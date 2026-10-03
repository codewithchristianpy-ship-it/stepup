from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class Skill(models.Model):
    """A thing someone can learn — e.g., Python Basics"""
    CATEGORY_CHOICES = [
        ('technology', 'Technology'),
        ('language', 'Languages'),
        ('math', 'Math & School'),
        ('career', 'Life & Career'),
        ('practical', 'Practical & Home'),
        ('creative', 'Creative & Arts'),
        ('health', 'Health & Wellness'),
        ('civic', 'Civic & Community'),
    ]
    DIFFICULTY_CHOICES = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
    ]

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, default='beginner')
    description = models.TextField(
        help_text="A short, friendly description of what this skill is."
    )
    icon = models.CharField(max_length=10, default='📘')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def total_learners(self):
        return self.links.count()

    @property
    def fresh_teachers(self):
        cutoff = timezone.now() - timedelta(days=90)
        return self.links.filter(learned_at__gte=cutoff, is_active=True).count()

    @property
    def official_lessons(self):
        """StepUp-authored lessons, in order."""
        return self.lessons.filter(is_official=True, status='official')

    @property
    def community_lessons(self):
        """Community lessons that are published and visible."""
        return self.lessons.filter(is_official=False, status='published')


class Lesson(models.Model):
    """A single lesson — either official (StepUp team) or community-contributed."""
    STATUS_CHOICES = [
        ('official', 'Official (StepUp Team)'),
        ('published', 'Community — Published'),
        ('pending', 'Community — Pending Review'),
        ('hidden', 'Community — Hidden (reported)'),
        ('rejected', 'Rejected'),
    ]

    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=200)
    content = models.TextField(help_text="Markdown or plain text. Keep it short and friendly.")
    order = models.PositiveIntegerField(default=1)
    estimated_minutes = models.PositiveIntegerField(default=5)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='lessons_written',
        help_text="Null for official StepUp lessons; set for community lessons."
    )
    is_official = models.BooleanField(default=False)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='official')
    review_reason = models.CharField(max_length=255, blank=True)
    quality_score = models.PositiveIntegerField(default=50)
    report_count = models.PositiveIntegerField(default=0)

    helpful_votes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['skill', 'is_official', 'order']

    def __str__(self):
        kind = "Official" if self.is_official else "Community"
        return f"[{kind}] {self.skill.name} — {self.title}"

    @property
    def is_community(self):
        return not self.is_official


class LearningLink(models.Model):
    """Someone who JUST learned a skill — they can now teach it."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='learning_links'
    )
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='links')
    learned_from = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='taught_links'
    )
    learned_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    is_self_taught = models.BooleanField(default=False)
    micro_proof = models.TextField(blank=True)

    class Meta:
        ordering = ['-learned_at']
        unique_together = ('user', 'skill')

    def __str__(self):
        return f"{self.user.username} → {self.skill.name}"

    @property
    def days_remaining(self):
        expiry = self.learned_at + timedelta(days=90)
        return max(0, (expiry - timezone.now()).days)

    @property
    def is_still_fresh(self):
        return self.days_remaining > 0


class StruggleLog(models.Model):
    """What confused you + what made it click — passed to the next learner."""
    link = models.OneToOneField(LearningLink, on_delete=models.CASCADE, related_name='struggle')
    biggest_confusion = models.TextField()
    breakthrough_moment = models.TextField()
    advice_to_past_self = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Struggle log for {self.link.user.username} on {self.link.skill.name}"


class LessonReport(models.Model):
    """A user's report of a community lesson."""
    REASONS = [
        ('spam', 'Spam / Promotion'),
        ('offensive', 'Offensive content'),
        ('wrong_skill', 'Wrong skill / off-topic'),
        ('copyright', 'Copyright violation'),
        ('other', 'Other'),
    ]

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='reports')
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_reports'
    )
    reason = models.CharField(max_length=20, choices=REASONS)
    details = models.TextField(blank=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('lesson', 'reporter')

    def __str__(self):
        return f"Report on {self.lesson.title} by {self.reporter.username}"