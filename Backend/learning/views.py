from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from agents.services import get_curriculum_recommendation
from xiavlearn.api import success_response

from .models import (
    LearnerProfile,
    Skill,
    CurriculumLevel,
    Module,
    SkillMastery,
    StudySession,
    StudyPlan,
)
from .serializers import (
    LearnerProfileSerializer,
    SkillSerializer,
    CurriculumLevelSerializer,
    ModuleSerializer,
    SkillMasterySerializer,
    StudySessionSerializer,
    StudyPlanSerializer,
)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def health_check(request):
    return Response({
        'status': 'ok',
        'message': 'XiAv Learn API is running'
    })


class ProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LearnerProfileSerializer

    def get_object(self):
        profile, _ = LearnerProfile.objects.get_or_create(user=self.request.user)
        return profile

    def patch(self, request, *args, **kwargs):
        return self.partial_update(request, *args, **kwargs)


class SkillListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    queryset = Skill.objects.all()
    serializer_class = SkillSerializer


class CurriculumLevelListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    queryset = CurriculumLevel.objects.all().order_by('sort_order')
    serializer_class = CurriculumLevelSerializer


class ModuleListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = ModuleSerializer

    def get_queryset(self):
        queryset = Module.objects.filter(is_active=True).select_related('level', 'skill')
        level_code = self.request.query_params.get('level_code')
        skill = self.request.query_params.get('skill')
        if level_code:
            queryset = queryset.filter(level__level_code__iexact=level_code)
        if skill:
            queryset = queryset.filter(skill__name__iexact=skill)
        return queryset


class ModuleDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    queryset = Module.objects.select_related('level', 'skill')
    serializer_class = ModuleSerializer


class DashboardView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        profile, _ = LearnerProfile.objects.get_or_create(user=request.user)
        profile_data = LearnerProfileSerializer(profile).data

        skill_mastery_qs = SkillMastery.objects.filter(user=request.user).select_related('skill')
        skill_mastery_data = SkillMasterySerializer(skill_mastery_qs, many=True).data

        latest_plan = StudyPlan.objects.filter(user=request.user).order_by('-generated_at').first()
        latest_plan_data = StudyPlanSerializer(latest_plan).data if latest_plan else None

        recent_sessions_qs = StudySession.objects.filter(user=request.user).order_by('-started_at')[:5].select_related('module__level', 'module__skill')
        recent_sessions_data = StudySessionSerializer(recent_sessions_qs, many=True).data
        recommendation = get_curriculum_recommendation(request.user)

        return success_response(
            {
                'profile': profile_data,
                'skill_mastery': skill_mastery_data,
                'recommended_module': recommendation['recommended_module'],
                'latest_study_plan': latest_plan_data,
                'recent_sessions': recent_sessions_data,
            },
            'Dashboard retrieved.',
        )
