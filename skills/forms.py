from django import forms
from django.utils import timezone
from .models import Session, LearningLink


class CreateSlotForm(forms.ModelForm):
    """Form for a Link to create an availability slot."""

    class Meta:
        model = Session
        fields = ['skill', 'scheduled_at', 'duration_minutes', 'notes']
        widgets = {
            'scheduled_at': forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local',
                    'class': 'form-control',
                },
                format='%Y-%m-%dT%H:%M',
            ),
            'skill': forms.Select(attrs={'class': 'form-select'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': 5, 'max': 60}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }
        labels = {
            'scheduled_at': 'When are you free?',
            'duration_minutes': 'How long? (minutes)',
            'notes': 'Optional notes for the learner',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            # Only show skills this user is a Link for
            skill_ids = LearningLink.objects.filter(
                user=user, is_active=True
            ).values_list('skill_id', flat=True)
            self.fields['skill'].queryset = self.fields['skill'].queryset.filter(id__in=skill_ids)

        self.fields['scheduled_at'].input_formats = ['%Y-%m-%dT%H:%M']

    def clean_scheduled_at(self):
        scheduled = self.cleaned_data['scheduled_at']
        # Allow any future time (even 1 min from now — helpful for testing)
        if scheduled < timezone.now():
            raise forms.ValidationError("Please pick a future time.")
        return scheduled

    def clean(self):
        cleaned = super().clean()
        scheduled = cleaned.get('scheduled_at')
        user = self.user if hasattr(self, 'user') else None

        if scheduled and user:
            # Prevent duplicate exact-time slots
            exists = Session.objects.filter(
                teacher=user,
                scheduled_at=scheduled,
                status='scheduled',
            ).exists()
            if exists:
                raise forms.ValidationError("You already have an open slot at that exact time.")

        return cleaned