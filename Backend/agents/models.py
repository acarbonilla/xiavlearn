from django.conf import settings
from django.db import models

from learning.models import StudySession


class LessonSession(models.Model):
    SESSION_MODE_TEXT = 'text'
    SESSION_MODE_SPEAKING = 'speaking'
    SESSION_MODE_LISTENING = 'listening'
    SESSION_MODE_PRONUNCIATION = 'pronunciation'
    SESSION_MODE_CHOICES = (
        (SESSION_MODE_TEXT, 'Text'),
        (SESSION_MODE_SPEAKING, 'Speaking'),
        (SESSION_MODE_LISTENING, 'Listening'),
        (SESSION_MODE_PRONUNCIATION, 'Pronunciation'),
    )

    study_session = models.OneToOneField(
        StudySession,
        on_delete=models.CASCADE,
        related_name='lesson_session',
    )
    lesson_text = models.TextField(blank=True)
    session_mode = models.CharField(
        max_length=32,
        choices=SESSION_MODE_CHOICES,
        default=SESSION_MODE_TEXT,
    )
    session_context = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, default='active')
    current_turn = models.PositiveIntegerField(default=1)
    final_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback_summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.study_session.user.username} - lesson session {self.pk}'


class LessonTurn(models.Model):
    session = models.ForeignKey(
        LessonSession,
        on_delete=models.CASCADE,
        related_name='turns',
    )
    turn_number = models.PositiveIntegerField()
    task_type = models.CharField(max_length=50, blank=True, default='')
    target_text = models.TextField(blank=True)
    target_focus = models.CharField(max_length=255, blank=True, default='')
    teacher_task = models.TextField()
    student_answer = models.TextField(blank=True)
    ai_feedback = models.TextField(blank=True)
    correction = models.TextField(blank=True)
    explanation = models.TextField(blank=True)
    encouragement = models.TextField(blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    evaluation_breakdown = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (('session', 'turn_number'),)
        ordering = ['turn_number', 'id']

    def __str__(self):
        return f'{self.session_id} turn {self.turn_number}'


class VoiceDiagnosticSession(models.Model):
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = (
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='voice_diagnostic_sessions',
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_IN_PROGRESS,
    )
    pronunciation_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    listening_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    speaking_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    recommended_focus = models.CharField(max_length=64, blank=True, default='')
    summary = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-started_at', '-id']

    def __str__(self):
        return f'{self.user.username} - voice diagnostic {self.pk}'


class VoiceDiagnosticItem(models.Model):
    SKILL_PRONUNCIATION = 'Pronunciation'
    SKILL_LISTENING = 'Listening'
    SKILL_SPEAKING = 'Speaking'
    SKILL_CHOICES = (
        (SKILL_PRONUNCIATION, 'Pronunciation'),
        (SKILL_LISTENING, 'Listening'),
        (SKILL_SPEAKING, 'Speaking'),
    )

    session = models.ForeignKey(
        VoiceDiagnosticSession,
        on_delete=models.CASCADE,
        related_name='items',
    )
    skill = models.CharField(max_length=64, choices=SKILL_CHOICES)
    item_number = models.PositiveIntegerField()
    task_type = models.CharField(max_length=64, blank=True, default='')
    prompt_text = models.TextField(blank=True, default='')
    target_text = models.TextField(blank=True, default='')
    passage_text = models.TextField(blank=True, default='')
    question_text = models.TextField(blank=True, default='')
    expected_answer = models.TextField(blank=True, default='')
    user_answer = models.TextField(blank=True, default='')
    transcript = models.TextField(blank=True, default='')
    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    feedback = models.TextField(blank=True, default='')
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        unique_together = (('session', 'skill', 'item_number'),)

    def __str__(self):
        return f'{self.session_id} {self.skill} item {self.item_number}'
