from django.contrib import admin
from .models import Skill, Lesson, LearningLink, StruggleLog, LessonReport


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    fields = ('order', 'title', 'estimated_minutes', 'content', 'is_official', 'author', 'status')
    ordering = ('order',)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('icon', 'name', 'category', 'difficulty', 'total_learners', 'fresh_teachers')
    list_filter = ('category', 'difficulty')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [LessonInline]


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('skill', 'order', 'title', 'status', 'is_official', 'author', 'quality_score', 'created_at')
    list_filter = ('status', 'is_official', 'skill__category')
    search_fields = ('title', 'content', 'skill__name', 'author__username')
    list_editable = ('status',)
    actions = ['approve_lessons', 'reject_lessons']

    def approve_lessons(self, request, queryset):
        author_emails = []
        for lesson in queryset.filter(status='pending'):
            if lesson.author:
                wallet = lesson.author.wallet
                wallet.add_credits(
                    amount=1,
                    description=f"Approved lesson: {lesson.title}",
                    transaction_type='earned_teaching',
                )
                profile = lesson.author.profile
                profile.approved_lesson_count += 1
                profile.update_trust_status()
                author_emails.append(lesson.author.email)

        queryset.update(status='published', review_reason='Approved by admin.')
        self.message_user(
            request,
            f"{queryset.count()} lessons approved. Credits awarded to {len(set(author_emails))} authors."
        )
    approve_lessons.short_description = "✅ Approve selected lessons"

    def reject_lessons(self, request, queryset):
        for lesson in queryset.filter(status='pending'):
            if lesson.author:
                profile = lesson.author.profile
                profile.rejected_lesson_count += 1
                profile.update_trust_status()

        queryset.update(status='rejected', review_reason='Rejected by admin.')
        self.message_user(request, f"{queryset.count()} lessons rejected.")
    reject_lessons.short_description = "❌ Reject selected lessons"


@admin.register(LearningLink)
class LearningLinkAdmin(admin.ModelAdmin):
    list_display = ('user', 'skill', 'learned_at', 'is_active', 'is_self_taught', 'days_remaining_display')
    list_filter = ('is_active', 'is_self_taught', 'skill')
    search_fields = ('user__username', 'user__email', 'skill__name')

    def days_remaining_display(self, obj):
        return f"{obj.days_remaining} days"
    days_remaining_display.short_description = "Fresh for"


@admin.register(StruggleLog)
class StruggleLogAdmin(admin.ModelAdmin):
    list_display = ('link', 'created_at')
    search_fields = ('link__user__username', 'link__skill__name')


@admin.register(LessonReport)
class LessonReportAdmin(admin.ModelAdmin):
    list_display = ('lesson', 'reporter', 'reason', 'created_at')
    list_filter = ('reason', 'created_at')
    search_fields = ('lesson__title', 'reporter__username', 'details')
    ordering = ('-created_at',)