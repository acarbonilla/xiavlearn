from rest_framework import serializers

from .models import (
    VoiceConversationSession,
    VoiceConversationTurn,
    VoiceDiagnosticItem,
    VoiceDiagnosticSession,
)


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


class VoiceConversationTurnSerializer(serializers.ModelSerializer):
    class Meta:
        model = VoiceConversationTurn
        fields = [
            'id',
            'turn_number',
            'user_transcript',
            'ai_response_text',
            'user_audio',
            'ai_audio',
            'transcript_source',
            'created_at',
            'metadata',
        ]
        read_only_fields = [
            'id',
            'turn_number',
            'created_at',
            'ai_response_text',
            'user_audio',
            'ai_audio',
        ]


class VoiceConversationSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = VoiceConversationSession
        fields = [
            'id',
            'title',
            'target_skill',
            'cefr_level',
            'status',
            'started_at',
            'ended_at',
            'summary',
            'final_feedback',
            'metadata',
        ]
        read_only_fields = [
            'id',
            'started_at',
            'ended_at',
            'status',
            'summary',
            'final_feedback',
        ]


class VoiceConversationSessionDetailSerializer(VoiceConversationSessionSerializer):
    turns = VoiceConversationTurnSerializer(many=True, read_only=True)

    class Meta(VoiceConversationSessionSerializer.Meta):
        fields = VoiceConversationSessionSerializer.Meta.fields + ['turns']


class VoiceConversationSessionStartSerializer(serializers.ModelSerializer):
    class Meta:
        model = VoiceConversationSession
        fields = [
            'title',
            'target_skill',
            'cefr_level',
            'metadata',
        ]


class VoiceConversationTurnCreateSerializer(serializers.Serializer):
    user_transcript = serializers.CharField(
        allow_blank=False,
        trim_whitespace=True,
        required=False,
    )
    user_audio = serializers.FileField(required=False, allow_empty_file=False, write_only=True)
    audio_file = serializers.FileField(required=False, allow_empty_file=False, write_only=True)
    transcript_source = serializers.ChoiceField(
        choices=[
            VoiceConversationTurn.TRANSCRIPT_SOURCE_MANUAL,
            VoiceConversationTurn.TRANSCRIPT_SOURCE_FALLBACK,
        ],
        default=VoiceConversationTurn.TRANSCRIPT_SOURCE_FALLBACK,
        required=False,
    )
    metadata = serializers.JSONField(required=False)

    def validate(self, attrs):
        user_transcript = attrs.get('user_transcript')
        user_audio = attrs.get('user_audio') or attrs.get('audio_file')

        if user_transcript and user_audio is not None:
            raise serializers.ValidationError(
                'Provide either user_transcript or audio_file, not both.'
            )
        if not user_transcript and user_audio is None:
            raise serializers.ValidationError(
                'Provide a non-empty user_transcript or audio_file.'
            )

        if user_audio is not None:
            attrs['user_audio'] = user_audio
            attrs['transcript_source'] = VoiceConversationTurn.TRANSCRIPT_SOURCE_DEEPGRAM
        return attrs
