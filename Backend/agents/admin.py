from django.contrib import admin

from .models import LessonSession, LessonTurn


@admin.register(LessonSession)
class LessonSessionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'study_session',
        'status',
        'current_turn',
        'final_score',
        'completed_at',
    )
    search_fields = ('study_session__user__username', 'study_session__module__title')


@admin.register(LessonTurn)
class LessonTurnAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'turn_number', 'score', 'created_at')
    search_fields = ('session__study_session__user__username', 'teacher_task')
