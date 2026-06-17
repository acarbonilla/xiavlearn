from django.db import models

from learning.models import StudySession


class LessonSession(models.Model):
    study_session = models.OneToOneField(
        StudySession,
        on_delete=models.CASCADE,
        related_name='lesson_session',
    )
    lesson_text = models.TextField(blank=True)
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
    teacher_task = models.TextField()
    student_answer = models.TextField(blank=True)
    ai_feedback = models.TextField(blank=True)
    correction = models.TextField(blank=True)
    explanation = models.TextField(blank=True)
    encouragement = models.TextField(blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (('session', 'turn_number'),)
        ordering = ['turn_number', 'id']

    def __str__(self):
        return f'{self.session_id} turn {self.turn_number}'
