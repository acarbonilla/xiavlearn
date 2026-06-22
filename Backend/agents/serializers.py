from rest_framework import serializers

from .models import VoiceDiagnosticItem, VoiceDiagnosticSession


def _serialize_score(value):
    if value is None:
        return None
    numeric = float(value)
    if numeric.is_integer():
        return int(numeric)
    return round(numeric, 2)


class VoiceDiagnosticItemSerializer(serializers.ModelSerializer):
    score = serializers.SerializerMethodField()

    class Meta:
        model = VoiceDiagnosticItem
        fields = [
            'id',
            'skill',
            'item_number',
            'task_type',
            'prompt_text',
            'target_text',
            'passage_text',
            'question_text',
            'expected_answer',
            'user_answer',
            'transcript',
            'score',
            'feedback',
            'details',
            'created_at',
        ]

    def get_score(self, obj):
        return _serialize_score(obj.score)


class VoiceDiagnosticSessionListSerializer(serializers.ModelSerializer):
    pronunciation_score = serializers.SerializerMethodField()
    listening_score = serializers.SerializerMethodField()
    speaking_score = serializers.SerializerMethodField()

    class Meta:
        model = VoiceDiagnosticSession
        fields = [
            'id',
            'status',
            'pronunciation_score',
            'listening_score',
            'speaking_score',
            'recommended_focus',
            'summary',
            'started_at',
            'completed_at',
        ]

    def get_pronunciation_score(self, obj):
        return _serialize_score(obj.pronunciation_score)

    def get_listening_score(self, obj):
        return _serialize_score(obj.listening_score)

    def get_speaking_score(self, obj):
        return _serialize_score(obj.speaking_score)


class VoiceDiagnosticSessionDetailSerializer(VoiceDiagnosticSessionListSerializer):
    items = VoiceDiagnosticItemSerializer(many=True, read_only=True)

    class Meta(VoiceDiagnosticSessionListSerializer.Meta):
        fields = VoiceDiagnosticSessionListSerializer.Meta.fields + ['items']
