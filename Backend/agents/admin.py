from django.contrib import admin

from .models import (
    LessonSession,
    LessonTurn,
    VoiceConversationSession,
    VoiceConversationTurn,
)


@admin.register(LessonSession)
class LessonSessionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'study_session',
        'session_mode',
        'status',
        'current_turn',
        'final_score',
        'completed_at',
    )
    search_fields = (
        'study_session__user__username',
        'study_session__module__title',
        'session_mode',
    )


@admin.register(LessonTurn)
class LessonTurnAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'turn_number', 'task_type', 'score', 'created_at')
    search_fields = ('session__study_session__user__username', 'teacher_task')


@admin.register(VoiceConversationSession)
class VoiceConversationSessionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'target_skill',
        'cefr_level',
        'status',
        'started_at',
        'ended_at',
    )
    search_fields = (
        'user__username',
        'title',
        'target_skill',
        'cefr_level',
        'status',
    )


@admin.register(VoiceConversationTurn)
class VoiceConversationTurnAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'session',
        'turn_number',
        'transcript_source',
        'created_at',
    )
    search_fields = (
        'session__user__username',
        'user_transcript',
        'ai_response_text',
        'transcript_source',
    )
