from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count

from .models import Skill, Lesson, LearningLink, StruggleLog


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
    """Show a single skill — lessons + chain + struggle logs."""
    skill = get_object_or_404(Skill, slug=slug)
    lessons = skill.lessons.all()

    # Fresh teachers (learned in last 90 days)
    from django.utils import timezone
    from datetime import timedelta
    cutoff = timezone.now() - timedelta(days=90)
    fresh_links = skill.links.filter(
        learned_at__gte=cutoff, is_active=True
    ).select_related('user', 'user__profile').order_by('-learned_at')

    # Recent struggle logs
    struggles = StruggleLog.objects.filter(
        link__skill=skill
    ).select_related('link__user').order_by('-created_at')[:10]

    # Does the current user already have a link for this skill?
    user_link = None
    if request.user.is_authenticated:
        user_link = LearningLink.objects.filter(user=request.user, skill=skill).first()

    context = {
        'skill': skill,
        'lessons': lessons,
        'fresh_links': fresh_links,
        'struggles': struggles,
        'user_link': user_link,
        'has_started_reading': bool(lessons.exists()),
    }
    return render(request, 'skills/detail.html', context)


def lesson_detail(request, slug, order):
    """Read a single lesson."""
    skill = get_object_or_404(Skill, slug=slug)
    lesson = get_object_or_404(Lesson, skill=skill, order=order)

    # Prev/next
    prev_lesson = skill.lessons.filter(order__lt=order).order_by('-order').first()
    next_lesson = skill.lessons.filter(order__gt=order).order_by('order').first()

    # Inline struggles relevant to this skill
    struggles = StruggleLog.objects.filter(
        link__skill=skill
    ).select_related('link__user').order_by('-created_at')[:3]

    total_lessons = skill.lessons.count()
    progress = int((order / total_lessons) * 100) if total_lessons else 0

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