from django.contrib import admin
from .models import Skill, Lesson, LearningLink, StruggleLog


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    fields = ('order', 'title', 'estimated_minutes', 'content')
    ordering = ('order',)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ('icon', 'name', 'category', 'difficulty', 'total_learners', 'fresh_teachers')
    list_filter = ('category', 'difficulty')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [LessonInline]


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