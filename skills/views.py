from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from .models import Skill, Lesson, LearningLink, StruggleLog, LessonReport
from .moderation import check_lesson, quality_score

def browse_skills(request):
    """List all skills with filters."""
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    difficulty = request.GET.get('difficulty', '').strip()
    sort = request.GET.get('sort', 'most_teachers')

    skills = Skill.objects.all()

    if query:
        skills = skills.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
    if category:
        skills = skills.filter(category=category)
    if difficulty:
        skills = skills.filter(difficulty=difficulty)

    # Annotate with counts for sorting
    skills = skills.annotate(
        _learners=Count('links', distinct=True),
    )

    if sort == 'most_learners':
        skills = skills.order_by('-_learners', 'name')
    elif sort == 'alphabetical':
        skills = skills.order_by('name')
    elif sort == 'newest':
        skills = skills.order_by('-created_at')
    else:  # most_teachers
        skills = skills.order_by('-_learners', 'name')

    context = {
        'skills': skills,
        'query': query,
        'category': category,
        'difficulty': difficulty,
        'sort': sort,
        'category_choices': Skill.CATEGORY_CHOICES,
        'difficulty_choices': Skill.DIFFICULTY_CHOICES,
    }
    return render(request, 'skills/browse.html', context)


def skill_detail(request, slug):
    """Show a single skill — official lessons, community lessons, chain, struggles."""
    skill = get_object_or_404(Skill, slug=slug)

    # Split lessons into official and community
    official_lessons = skill.lessons.filter(
        is_official=True, status='official'
    ).order_by('order')

    community_lessons = skill.lessons.filter(
        is_official=False, status='published'
    ).select_related('author').order_by('-helpful_votes', '-created_at')

    # Fresh teachers (learned in last 90 days)
    cutoff = timezone.now() - timedelta(days=90)
    fresh_links = skill.links.filter(
        learned_at__gte=cutoff, is_active=True
    ).select_related('user', 'user__profile').order_by('-learned_at')

    # Recent struggle logs
    struggles = StruggleLog.objects.filter(
        link__skill=skill
    ).select_related('link__user').order_by('-created_at')[:10]

    # Does the current user have a link for this skill?
    user_link = None
    if request.user.is_authenticated:
        user_link = LearningLink.objects.filter(user=request.user, skill=skill).first()

    # Eligibility to add a lesson: viewed at least 1 lesson OR has a link
    can_add_lesson = False
    if request.user.is_authenticated:
        has_viewed = request.session.get(f'viewed_lesson_{skill.slug}', False)
        can_add_lesson = has_viewed or (user_link is not None)

    context = {
        'skill': skill,
        'official_lessons': official_lessons,
        'community_lessons': community_lessons,
        'fresh_links': fresh_links,
        'struggles': struggles,
        'user_link': user_link,
        'has_started_reading': official_lessons.exists(),
        'can_add_lesson': can_add_lesson,
    }
    return render(request, 'skills/detail.html', context)


def lesson_detail(request, slug, order):
    """Read a single lesson. Track viewing for add-lesson eligibility."""
    skill = get_object_or_404(Skill, slug=slug)
    lesson = get_object_or_404(Lesson, skill=skill, order=order)

    # Only show prev/next within the SAME section (official vs community)
    same_section = skill.lessons.filter(is_official=lesson.is_official, status=lesson.status)
    prev_lesson = same_section.filter(order__lt=order).order_by('-order').first()
    next_lesson = same_section.filter(order__gt=order).order_by('order').first()

    # Inline struggles relevant to this skill
    struggles = StruggleLog.objects.filter(
        link__skill=skill
    ).select_related('link__user').order_by('-created_at')[:3]

    total_lessons = same_section.count()
    progress = int((order / total_lessons) * 100) if total_lessons else 0

    # Track that this user opened a lesson of this skill
    if request.user.is_authenticated:
        request.session[f'viewed_lesson_{skill.slug}'] = True

    context = {
        'skill': skill,
        'lesson': lesson,
        'prev_lesson': prev_lesson,
        'next_lesson': next_lesson,
        'struggles': struggles,
        'total_lessons': total_lessons,
        'progress': progress,
    }
    return render(request, 'skills/lesson.html', context)

@login_required
def mark_as_learned(request, slug):
    """User clicks 'I just learned this!' → becomes a Link."""
    skill = get_object_or_404(Skill, slug=slug)

    if request.method != 'POST':
        return redirect('skills:detail', slug=slug)

    if LearningLink.objects.filter(user=request.user, skill=skill).exists():
        messages.info(request, "You've already marked this skill as learned.")
        return redirect('skills:detail', slug=slug)

    # Optional: capture struggle log
    confusion = request.POST.get('biggest_confusion', '').strip()
    breakthrough = request.POST.get('breakthrough_moment', '').strip()
    advice = request.POST.get('advice_to_past_self', '').strip()
    proof = request.POST.get('micro_proof', '').strip()

    link = LearningLink.objects.create(
        user=request.user,
        skill=skill,
        is_self_taught=True,
        micro_proof=proof,
    )

    if confusion and breakthrough and advice:
        StruggleLog.objects.create(
            link=link,
            biggest_confusion=confusion,
            breakthrough_moment=breakthrough,
            advice_to_past_self=advice,
        )

    # Update user role if they were just a learner
    profile = request.user.profile
    if profile.role == 'learner':
        profile.role = 'link'
        profile.save()

    messages.success(
        request,
        f"🎉 You're now a Link for {skill.name}! You can teach someone one step behind you."
    )
    return redirect('skills:detail', slug=slug)


@login_required
def add_lesson(request, slug):
    """
    Community member submits a lesson.
    Flow:
      1. Eligibility: user must have viewed at least 1 lesson of this skill.
      2. Moderation runs (skill-aware).
      3. Verdict: reject / review / pass.
      4. Trust: trusted contributors auto-publish on pass; others go to pending.
      5. Credit: awarded on publish.
    """
    skill = get_object_or_404(Skill, slug=slug)
    profile = request.user.profile

    # === ELIGIBILITY CHECK ===
    has_viewed = request.session.get(f'viewed_lesson_{skill.slug}', False)
    has_link = LearningLink.objects.filter(user=request.user, skill=skill).exists()

    if not has_viewed and not has_link:
        messages.warning(
            request,
            f"Please read at least one lesson of {skill.name} before adding your own. "
            f"Start with Lesson 1."
        )
        return redirect('skills:lesson', slug=skill.slug, order=1)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        minutes_raw = request.POST.get('estimated_minutes', '5').strip()

        try:
            minutes = int(minutes_raw)
            if minutes < 1 or minutes > 60:
                minutes = 5
        except ValueError:
            minutes = 5

        # === MODERATION ===
        verdict, reason = check_lesson(title, content, skill)

        if verdict == 'reject':
            messages.error(request, f"❌ {reason}")
            return render(request, 'skills/add_lesson.html', {
                'skill': skill,
                'title': title,
                'content': content,
                'minutes': minutes_raw,
            })

        score = quality_score(title, content, skill)

        # === ORDER: community lessons get order 100+ ===
        existing_community = skill.lessons.filter(is_official=False).count()
        new_order = 100 + existing_community + 1

        # === DECIDE STATUS ===
        if verdict == 'review':
            status = 'pending'
        else:  # verdict == 'pass'
            if profile.can_auto_publish:
                status = 'published'
            else:
                status = 'pending'
                reason = "New contributor — your first lessons need review. Thanks for your patience!"

        # === CREATE LESSON ===
        lesson = Lesson.objects.create(
            skill=skill,
            title=title,
            content=content,
            order=new_order,
            estimated_minutes=minutes,
            author=request.user,
            is_official=False,
            status=status,
            review_reason=reason or '',
            quality_score=score,
        )

        # === REWARD ===
        if status == 'published':
            wallet = request.user.wallet
            wallet.add_credits(
                amount=1,
                description=f"Thanks for adding a lesson to {skill.name}!",
                transaction_type='earned_teaching',
            )
            profile.approved_lesson_count += 1
            profile.update_trust_status()
            messages.success(
                request,
                "🎉 Lesson published! You earned 1 credit for helping the community."
            )
            return redirect('skills:lesson', slug=skill.slug, order=lesson.order)
        else:
            messages.info(
                request,
                "📝 Thanks! Your lesson was received and is now pending review. "
                "You'll earn 1 credit once it's approved."
            )
            return redirect('skills:my_lessons')

    return render(request, 'skills/add_lesson.html', {'skill': skill})




@login_required
def my_lessons(request):
    """User sees their own lessons — published, pending, and rejected."""
    lessons = Lesson.objects.filter(
        author=request.user,
        is_official=False,
    ).select_related('skill').order_by('-created_at')

    context = {
        'lessons': lessons,
        'published_count': lessons.filter(status='published').count(),
        'pending_count': lessons.filter(status='pending').count(),
        'rejected_count': lessons.filter(status='rejected').count(),
    }
    return render(request, 'skills/my_lessons.html', context)

@login_required
def report_lesson(request, slug, order):
    """User reports a community lesson."""
    skill = get_object_or_404(Skill, slug=slug)
    lesson = get_object_or_404(Lesson, skill=skill, order=order, is_official=False)

    # Can't report your own lesson
    if lesson.author == request.user:
        messages.warning(request, "You can't report your own lesson.")
        return redirect('skills:lesson', slug=skill.slug, order=lesson.order)

    # Can't report already-hidden lessons
    if lesson.status == 'hidden':
        messages.info(request, "This lesson is already under review. Thanks!")
        return redirect('skills:lesson', slug=skill.slug, order=lesson.order)

    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        details = request.POST.get('details', '').strip()

        valid_reasons = [r[0] for r in LessonReport.REASONS]
        if reason not in valid_reasons:
            messages.error(request, "Please choose a valid reason.")
            return redirect('skills:lesson', slug=skill.slug, order=lesson.order)

        # Create report (unique_together prevents duplicates)
        report, created = LessonReport.objects.get_or_create(
            lesson=lesson,
            reporter=request.user,
            defaults={'reason': reason, 'details': details}
        )

        if not created:
            messages.info(request, "You've already reported this lesson.")
            return redirect('skills:lesson', slug=skill.slug, order=lesson.order)

        # Update report count
        lesson.report_count = lesson.reports.count()
        lesson.save()

        # === AUTO-HIDE THRESHOLD ===
        if lesson.report_count >= 3:
            lesson.status = 'hidden'
            lesson.review_reason = f"Auto-hidden: {lesson.report_count} user reports."
            lesson.save()

            # Reduce author's trust
            if lesson.author:
                author_profile = lesson.author.profile
                author_profile.is_flagged = True
                author_profile.save()

            messages.warning(
                request,
                "Thanks for the report. This lesson has been hidden and is now under review."
            )
        else:
            messages.success(
                request,
                f"Report submitted. {3 - lesson.report_count} more reports will hide this lesson."
            )

        return redirect('skills:lesson', slug=skill.slug, order=lesson.order)

    # GET → show confirmation page
    return render(request, 'skills/report_lesson.html', {
        'skill': skill,
        'lesson': lesson,
        'reasons': LessonReport.REASONS,
    })


@login_required
def vote_lesson_helpful(request, slug, order):
    """User marks a lesson as helpful — boosts its visibility."""
    if request.method != 'POST':
        return redirect('skills:lesson', slug=slug, order=order)

    skill = get_object_or_404(Skill, slug=slug)
    lesson = get_object_or_404(Lesson, skill=skill, order=order)

    lesson.helpful_votes += 1
    lesson.save()

    messages.success(request, "Thanks for the feedback!")
    return redirect('skills:lesson', slug=slug, order=order)