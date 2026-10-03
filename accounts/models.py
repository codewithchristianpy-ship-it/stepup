
from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user — email required & unique."""
    email = models.EmailField(unique=True)
    is_email_verified = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email


class Profile(models.Model):
    ROLE_CHOICES = [
        ('learner', 'Learner'),
        ('link', 'Link (recently learned, can teach)'),
        ('mentor', 'Mentor'),
        ('sponsor', 'Sponsor'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='learner')
    bio = models.TextField(blank=True, max_length=500)
    country = models.CharField(max_length=100, blank=True)
    timezone_name = models.CharField(max_length=100, blank=True, default='UTC')
    languages = models.CharField(
        max_length=200, blank=True,
        help_text="Comma-separated, e.g. English, Yoruba, French"
    )
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # === Trust & moderation fields ===
    approved_lesson_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of lessons this user has written that were approved/published."
    )
    rejected_lesson_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of lessons this user has written that were rejected."
    )
    is_trusted_contributor = models.BooleanField(
        default=False,
        help_text="True after 3+ approved lessons. Trusted users get instant publishing."
    )
    is_flagged = models.BooleanField(
        default=False,
        help_text="True if the user has been reported recently. Forces all lessons to review."
    )

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def can_auto_publish(self):
        """Trusted AND not currently flagged → can auto-publish."""
        return self.is_trusted_contributor and not self.is_flagged

    def update_trust_status(self):
        """Call after a lesson is approved or rejected."""
        if self.approved_lesson_count >= 3 and self.rejected_lesson_count < 3:
            self.is_trusted_contributor = True
        else:
            self.is_trusted_contributor = False

        # If user has 3+ rejections in a row (simple heuristic), flag them
        if self.rejected_lesson_count >= 3 and self.approved_lesson_count < self.rejected_lesson_count:
            self.is_flagged = True

        self.save()