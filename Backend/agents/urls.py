from django.urls import path

from .views import (
    CoachSummaryView,
    CurriculumRecommendationView,
    DiagnosticEvaluateView,
    SchedulerGeneratePlanView,
    TeacherFeedbackView,
    TeacherSessionView,
)
from .voice_views import (
    ListeningEvaluateView,
    PronunciationEvaluateView,
    SpeakingEvaluateView,
    VoiceDiagnosticPromptsView,
    VoiceDiagnosticTTSView,
)


urlpatterns = [
    path(
        'diagnostic/evaluate/',
        DiagnosticEvaluateView.as_view(),
        name='diagnostic-evaluate',
    ),
    path(
        'curriculum/recommendation/',
        CurriculumRecommendationView.as_view(),
        name='curriculum-recommendation',
    ),
    path(
        'teacher/session/',
        TeacherSessionView.as_view(),
        name='teacher-session',
    ),
    path(
        'teacher/feedback/',
        TeacherFeedbackView.as_view(),
        name='teacher-feedback',
    ),
    path(
        'scheduler/generate-plan/',
        SchedulerGeneratePlanView.as_view(),
        name='scheduler-generate-plan',
    ),
    path(
        'coach/summary/',
        CoachSummaryView.as_view(),
        name='coach-summary',
    ),
    path(
        'voice-diagnostic/prompts/',
        VoiceDiagnosticPromptsView.as_view(),
        name='voice-diagnostic-prompts',
    ),
    path(
        'voice-diagnostic/tts/',
        VoiceDiagnosticTTSView.as_view(),
        name='voice-diagnostic-tts',
    ),
    path(
        'voice-diagnostic/pronunciation/evaluate/',
        PronunciationEvaluateView.as_view(),
        name='voice-diagnostic-pronunciation-evaluate',
    ),
    path(
        'voice-diagnostic/listening/evaluate/',
        ListeningEvaluateView.as_view(),
        name='voice-diagnostic-listening-evaluate',
    ),
    path(
        'voice-diagnostic/speaking/evaluate/',
        SpeakingEvaluateView.as_view(),
        name='voice-diagnostic-speaking-evaluate',
    ),
]
