from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from datetime import timedelta

from .models import Skill, Lesson, LearningLink, StruggleLog, LessonReport, Session
from .moderation import check_lesson, quality_score
from .forms import CreateSlotForm


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

    skills = skills.annotate(_learners=Count('links', distinct=True))

    if sort == 'most_learners':
        skills = skills.order_by('-_learners', 'name')
    elif sort == 'alphabetical':
        skills = skills.order_by('name')
    elif sort == 'newest':
        skills = skills.order_by('-created_at')
    else:
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

    official_lessons = skill.lessons.filter(
        is_official=True, status='official'
    ).order_by('order')

    community_lessons = skill.lessons.filter(
        is_official=False, status='published'
    ).select_related('author').order_by('-helpful_votes', '-created_at')

    cutoff = timezone.now() - timedelta(days=90)
    fresh_links = skill.links.filter(
        learned_at__gte=cutoff, is_active=True
    ).select_related('user', 'user__profile').order_by('-learned_at')

    struggles = StruggleLog.objects.filter(
        link__skill=skill
    ).select_related('link__user').order_by('-created_at')[:10]

    user_link = None
    if request.user.is_authenticated:
        user_link = LearningLink.objects.filter(user=request.user, skill=skill).first()

    can_add_lesson = False
    if request.user.is_authenticated:
        has_viewed = request.session.get(f'viewed_lesson_{skill.slug}', False)
        can_add_lesson = has_viewed or (user_link is not None)

    now = timezone.now()
    open_slots = Session.objects.filter(
        skill=skill,
        status='scheduled',
        learner__isnull=True,
        scheduled_at__gte=now,
    ).select_related('teacher', 'teacher__profile').order_by('scheduled_at')[:10]

    context = {
        'skill': skill,
        'official_lessons': official_lessons,
        'community_lessons': community_lessons,
        'fresh_links': fresh_links,
        'struggles': struggles,
        'user_link': user_link,
        'has_started_reading': official_lessons.exists(),
        'can_add_lesson': can_add_lesson,
        'open_slots': open_slots,
    }
    return render(request, 'skills/detail.html', context)


def lesson_detail(request, slug, order):
    """Read a single lesson. Track viewing for add-lesson eligibility."""
    skill = get_object_or_404(Skill, slug=slug)
    lesson = get_object_or_404(Lesson, skill=skill, order=order)

    same_section = skill.lessons.filter(is_official=lesson.is_official, status=lesson.status)
    prev_lesson = same_section.filter(order__lt=order).order_by('-order').first()
    next_lesson = same_section.filter(order__gt=order).order_by('order').first()

    struggles = StruggleLog.objects.filter(
        link__skill=skill
    ).select_related('link__user').order_by('-created_at')[:3]

    total_lessons = same_section.count()
    progress = int((order / total_lessons) * 100) if total_lessons else 0

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
    """Community member submits a lesson."""
    skill = get_object_or_404(Skill, slug=slug)
    profile = request.user.profile

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

        existing_community = skill.lessons.filter(is_official=False).count()
        new_order = 100 + existing_community + 1

        if verdict == 'review':
            status = 'pending'
        else:
            if profile.can_auto_publish:
                status = 'published'
            else:
                status = 'pending'
                reason = "New contributor — first lessons need review."

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
def vote_lesson_helpful(request, slug, order):
    """User marks a lesson as helpful."""
    if request.method != 'POST':
        return redirect('skills:lesson', slug=slug, order=order)

    skill = get_object_or_404(Skill, slug=slug)
    lesson = get_object_or_404(Lesson, skill=skill, order=order)

    lesson.helpful_votes += 1
    lesson.save()

    messages.success(request, "Thanks for the feedback!")
    return redirect('skills:lesson', slug=slug, order=order)


@login_required
def report_lesson(request, slug, order):
    """User reports a community lesson."""
    skill = get_object_or_404(Skill, slug=slug)
    lesson = get_object_or_404(Lesson, skill=skill, order=order, is_official=False)

    if lesson.author == request.user:
        messages.warning(request, "You can't report your own lesson.")
        return redirect('skills:lesson', slug=skill.slug, order=lesson.order)

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

        report, created = LessonReport.objects.get_or_create(
            lesson=lesson,
            reporter=request.user,
            defaults={'reason': reason, 'details': details}
        )

        if not created:
            messages.info(request, "You've already reported this lesson.")
            return redirect('skills:lesson', slug=skill.slug, order=lesson.order)

        lesson.report_count = lesson.reports.count()
        lesson.save()

        if lesson.report_count >= 3:
            lesson.status = 'hidden'
            lesson.review_reason = f"Auto-hidden: {lesson.report_count} user reports."
            lesson.save()

            if lesson.author:
                author_profile = lesson.author.profile
                author_profile.is_flagged = True
                author_profile.save()

            messages.warning(request, "Thanks for the report. This lesson has been hidden and is now under review.")
        else:
            messages.success(request, f"Report submitted. {3 - lesson.report_count} more reports will hide this lesson.")

        return redirect('skills:lesson', slug=skill.slug, order=lesson.order)

    return render(request, 'skills/report_lesson.html', {
        'skill': skill,
        'lesson': lesson,
        'reasons': LessonReport.REASONS,
    })


@login_required
def create_slot(request):
    """A Link creates an availability slot."""
    links = LearningLink.objects.filter(user=request.user, is_active=True)
    if not links.exists():
        messages.warning(
            request,
            "You need to be a Link for at least one skill before offering sessions."
        )
        return redirect('skills:browse')

    if request.method == 'POST':
        form = CreateSlotForm(request.POST, user=request.user)
        form.user = request.user
        if form.is_valid():
            session = form.save(commit=False)
            session.teacher = request.user
            session.status = 'scheduled'
            session.save()
            messages.success(
                request,
                f"🎉 Slot created for {session.skill.name} on "
                f"{session.scheduled_at.strftime('%b %d at %H:%M')}!"
            )
            return redirect('skills:my_sessions')
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = CreateSlotForm(user=request.user)
        form.user = request.user

    return render(request, 'skills/create_slot.html', {'form': form})


@login_required
def my_sessions(request):
    """Teacher sees sessions + upcoming bookings as learner."""
    now = timezone.now()

    teaching_open = Session.objects.filter(
        teacher=request.user, status='scheduled', learner__isnull=True
    ).select_related('skill').order_by('scheduled_at')

    teaching_confirmed = Session.objects.filter(
        teacher=request.user, status='confirmed', scheduled_at__gte=now
    ).select_related('skill', 'learner').order_by('scheduled_at')

    teaching_past = Session.objects.filter(
        teacher=request.user, status__in=['completed', 'cancelled', 'no_show']
    ).select_related('skill', 'learner').order_by('-scheduled_at')[:10]

    learning_upcoming = Session.objects.filter(
        learner=request.user, status='confirmed', scheduled_at__gte=now
    ).select_related('skill', 'teacher').order_by('scheduled_at')

    learning_past = Session.objects.filter(
        learner=request.user, status='completed'
    ).select_related('skill', 'teacher').order_by('-scheduled_at')[:10]

    context = {
        'teaching_open': teaching_open,
        'teaching_confirmed': teaching_confirmed,
        'teaching_past': teaching_past,
        'learning_upcoming': learning_upcoming,
        'learning_past': learning_past,
    }
    return render(request, 'skills/my_sessions.html', context)


@login_required
def book_slot(request, session_id):
    """A learner books an open slot. Transfers 1 credit to teacher."""
    session = get_object_or_404(Session, id=session_id)

    if not session.is_open:
        messages.error(request, "This slot is no longer available.")
        return redirect('skills:detail', slug=session.skill.slug)

    if session.teacher == request.user:
        messages.error(request, "You can't book your own slot.")
        return redirect('skills:detail', slug=session.skill.slug)

    wallet = request.user.wallet
    if wallet.balance < 1:
        messages.error(
            request,
            "You need at least 1 credit to book a session."
        )
        return redirect('skills:detail', slug=session.skill.slug)

    if request.method == 'POST':
        try:
            wallet.spend_credits(
                amount=1,
                description=f"Booked session with {session.teacher.username} for {session.skill.name}",
            )
        except ValueError:
            messages.error(request, "Not enough credits.")
            return redirect('skills:detail', slug=session.skill.slug)

        session.learner = request.user
        session.status = 'confirmed'
        session.credits_paid = True
        session.save()

        messages.success(
            request,
            f"🎉 Session booked with {session.teacher.profile.display_name}!"
        )
        return redirect('skills:session_detail', session_id=session.id)

    return render(request, 'skills/book_slot.html', {'session': session})


@login_required
def session_detail(request, session_id):
    """Session detail page — Jitsi room link, participant info, actions."""
    session = get_object_or_404(Session, id=session_id)

    if request.user != session.teacher and request.user != session.learner:
        messages.error(request, "You don't have access to this session.")
        return redirect('skills:my_sessions')

    now = timezone.now()

    join_window_start = session.scheduled_at - timedelta(minutes=5)
    join_window_end = session.scheduled_at + timedelta(minutes=session.duration_minutes + 15)
    can_join = join_window_start <= now <= join_window_end

    is_teacher = request.user == session.teacher
    is_learner = request.user == session.learner

    context = {
        'session': session,
        'is_teacher': is_teacher,
        'is_learner': is_learner,
        'can_join': can_join,
        'join_window_start': join_window_start,
        'join_window_end': join_window_end,
    }
    return render(request, 'skills/session_detail.html', context)


@login_required
def complete_session(request, session_id):
    """Mark a confirmed session as completed."""
    session = get_object_or_404(Session, id=session_id)

    if request.user != session.teacher and request.user != session.learner:
        return redirect('skills:my_sessions')

    if session.status != 'confirmed':
        messages.error(request, "This session can't be marked complete.")
        return redirect('skills:session_detail', session_id=session.id)

    if request.method == 'POST':
        session.status = 'completed'
        session.completed_at = timezone.now()
        session.save()

        messages.success(request, "✅ Session marked complete. Thanks!")
        return redirect('skills:session_detail', session_id=session.id)

    return render(request, 'skills/complete_session.html', {'session': session})


@login_required
def cancel_session(request, session_id):
    """Cancel a confirmed session and refund the learner."""
    session = get_object_or_404(Session, id=session_id)

    if request.user != session.teacher and request.user != session.learner:
        return redirect('skills:my_sessions')

    if session.status not in ['confirmed', 'scheduled']:
        messages.error(request, "This session can't be cancelled.")
        return redirect('skills:session_detail', session_id=session.id)

    if request.method == 'POST':
        if session.credits_paid and session.learner and not session.credits_refunded:
            wallet = session.learner.wallet
            wallet.add_credits(
                amount=1,
                description=f"Refund: cancelled session with {session.teacher.username}",
                transaction_type='received',
            )
            session.credits_refunded = True

        session.status = 'cancelled'
        session.save()

        messages.info(request, "Session cancelled. Learner refunded.")
        return redirect('skills:my_sessions')

    return render(request, 'skills/cancel_session.html', {'session': session})


@login_required
def submit_feedback(request, session_id):
    """Learner or teacher leaves feedback after a completed session."""
    session = get_object_or_404(Session, id=session_id)

    if request.user != session.teacher and request.user != session.learner:
        return redirect('skills:my_sessions')

    if session.status != 'completed':
        messages.error(request, "You can only leave feedback after a session is completed.")
        return redirect('skills:session_detail', session_id=session.id)

    if request.method == 'POST':
        rating = request.POST.get('rating', '').strip()
        feedback = request.POST.get('feedback', '').strip()[:1000]

        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                raise ValueError
        except (ValueError, TypeError):
            messages.error(request, "Please pick a rating between 1 and 5.")
            return redirect('skills:session_detail', session_id=session.id)

        if request.user == session.teacher:
            if session.teacher_rating:
                messages.info(request, "You've already left feedback for this session.")
                return redirect('skills:session_detail', session_id=session.id)
            session.teacher_rating = rating
            session.teacher_feedback = feedback
        else:
            if session.learner_rating:
                messages.info(request, "You've already left feedback for this session.")
                return redirect('skills:session_detail', session_id=session.id)
            session.learner_rating = rating
            session.learner_feedback = feedback

        session.save()
        messages.success(request, "🎉 Thanks for your feedback!")
        return redirect('skills:session_detail', session_id=session.id)

    return redirect('skills:session_detail', session_id=session.id)