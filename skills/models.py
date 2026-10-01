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
    icon = models.CharField(
        max_length=10, default='📘',
        help_text="A single emoji representing this skill."
    )
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
        """How many people have ever learned this skill on StepUp."""
        return self.links.count()

    @property
    def fresh_teachers(self):
        """How many people can teach this RIGHT NOW (learned in last 90 days)."""
        cutoff = timezone.now() - timedelta(days=90)
        return self.links.filter(learned_at__gte=cutoff, is_active=True).count()

    @property
    def lesson_count(self):
        return self.lessons.count()

    @property
    def chain_depth(self):
        """How many levels deep the longest chain goes."""
        # Simple version: longest path from a root to any link
        # For MVP: just return total learners as approximation
        return self.links.count()


class Lesson(models.Model):
    """A single reading lesson for a skill."""
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=200)
    content = models.TextField(help_text="Markdown or plain text. Keep it short and friendly.")
    order = models.PositiveIntegerField(default=1)
    estimated_minutes = models.PositiveIntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['skill', 'order']
        unique_together = ('skill', 'order')

    def __str__(self):
        return f"{self.skill.name} — Lesson {self.order}: {self.title}"


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
    is_self_taught = models.BooleanField(
        default=False,
        help_text="True if they learned by reading lessons alone."
    )
    micro_proof = models.TextField(
        blank=True,
        help_text="A short description or link proving they can do this."
    )

    class Meta:
        ordering = ['-learned_at']
        # One active link per user per skill
        unique_together = ('user', 'skill')

    def __str__(self):
        return f"{self.user.username} → {self.skill.name}"

    @property
    def days_remaining(self):
        """Days left until this link is 'too old' to teach."""
        expiry = self.learned_at + timedelta(days=90)
        return max(0, (expiry - timezone.now()).days)

    @property
    def is_still_fresh(self):
        return self.days_remaining > 0


class StruggleLog(models.Model):
    """What confused you + what made it click — passed to the next learner."""
    link = models.OneToOneField(LearningLink, on_delete=models.CASCADE, related_name='struggle')
    biggest_confusion = models.TextField(
        help_text="What confused you most while learning?"
    )
    breakthrough_moment = models.TextField(
        help_text="What finally made it click?"
    )
    advice_to_past_self = models.TextField(
        help_text="What would you tell yourself before starting?"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Struggle log for {self.link.user.username} on {self.link.skill.name}"