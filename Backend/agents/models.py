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
