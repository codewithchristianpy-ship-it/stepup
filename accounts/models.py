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

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def display_name(self):
        return self.user.get_full_name() or self.user.username