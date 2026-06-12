from rest_framework import serializers
from .models import (
    LearnerProfile,
    Skill,
    CurriculumLevel,
    Module,
    SkillMastery,
    StudySession,
    StudyPlan,
)


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ['id', 'name', 'description']


class CurriculumLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurriculumLevel
        fields = ['id', 'level_code', 'name', 'description', 'sort_order']


class ModuleSerializer(serializers.ModelSerializer):
    level = CurriculumLevelSerializer(read_only=True)
    skill = SkillSerializer(read_only=True)

    class Meta:
        model = Module
        fields = ['id', 'title', 'description', 'level', 'skill', 'objectives', 'sort_order']


class LearnerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearnerProfile
        fields = [
            'id',
            'user',
            'current_level',
            'target_level',
            'daily_study_minutes',
            'learning_goal',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'current_level', 'created_at', 'updated_at']


class SkillMasterySerializer(serializers.ModelSerializer):
    skill = SkillSerializer(read_only=True)

    class Meta:
        model = SkillMastery
        fields = ['id', 'skill', 'level_code', 'score', 'status', 'last_updated']


class StudySessionSerializer(serializers.ModelSerializer):
    module = ModuleSerializer(read_only=True)

    class Meta:
        model = StudySession
        fields = [
            'id',
            'module',
            'session_type',
            'input_text',
            'ai_feedback',
            'score',
            'started_at',
            'completed_at',
        ]


class StudyPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyPlan
        fields = [
            'id',
            'plan_data',
            'focus_skills',
            'start_date',
            'end_date',
            'generated_at',
        ]
