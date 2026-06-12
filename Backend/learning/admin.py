from django.contrib import admin
from .models import (
	LearnerProfile,
	Skill,
	SkillMastery,
	CurriculumLevel,
	Module,
	StudySession,
	StudyPlan,
)


@admin.register(LearnerProfile)
class LearnerProfileAdmin(admin.ModelAdmin):
	list_display = ('user', 'current_level', 'target_level', 'daily_study_minutes')
	search_fields = ('user__username',)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
	list_display = ('name', 'created_at')
	search_fields = ('name',)


@admin.register(SkillMastery)
class SkillMasteryAdmin(admin.ModelAdmin):
	list_display = ('user', 'skill', 'level_code', 'score', 'status', 'last_updated')
	search_fields = ('user__username', 'skill__name')


@admin.register(CurriculumLevel)
class CurriculumLevelAdmin(admin.ModelAdmin):
	list_display = ('level_code', 'name', 'sort_order')
	search_fields = ('level_code', 'name')


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
	list_display = ('title', 'level', 'skill', 'is_active', 'sort_order')
	search_fields = ('title', 'skill__name')
	list_filter = ('is_active', 'level')


@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
	list_display = ('user', 'session_type', 'module', 'started_at', 'completed_at')
	search_fields = ('user__username', 'module__title')


@admin.register(StudyPlan)
class StudyPlanAdmin(admin.ModelAdmin):
	list_display = ('user', 'generated_at')
	search_fields = ('user__username',)
