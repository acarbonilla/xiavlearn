import json
import re
from decimal import Decimal
from difflib import SequenceMatcher
from urllib import error, parse, request

from django.conf import settings
from django.db import transaction

from learning.models import Skill, SkillMastery


PRONUNCIATION_TARGET_SENTENCE = (
    'I want to improve my English communication skills for work and daily conversations.'
)


class VoiceDiagnosticError(Exception):
    pass


class VoiceDiagnosticConfigError(VoiceDiagnosticError):
    pass


def get_voice_diagnostic_prompts():
    return {
        'pronunciation': {
            'target_sentence': PRONUNCIATION_TARGET_SENTENCE,
        },
    }


def _voice_diagnostic_is_configured():
    return bool(
        getattr(settings, 'USE_VOICE_DIAGNOSTIC', False)
        and getattr(settings, 'DEEPGRAM_API_KEY', '')
    )


def synthesize_tts(text):
    text = (text or '').strip()
    if not text:
        raise VoiceDiagnosticError('text must be a non-empty string.')
    if not _voice_diagnostic_is_configured():
        raise VoiceDiagnosticConfigError('TTS is not configured yet.')

    model = getattr(settings, 'DEEPGRAM_TTS_MODEL', 'aura-2-thalia-en')
    query = parse.urlencode({'model': model})
    url = f'https://api.deepgram.com/v1/speak?{query}'
    payload = json.dumps({'text': text}).encode('utf-8')
    http_request = request.Request(
        url,
        data=payload,
        method='POST',
        headers={
            'Authorization': f'Token {settings.DEEPGRAM_API_KEY}',
            'Accept': 'audio/mpeg',
            'Content-Type': 'application/json',
        },
    )

    try:
        with request.urlopen(http_request, timeout=30) as response:
            content_type = response.headers.get('Content-Type') or 'audio/mpeg'
            return response.read(), content_type
    except (error.HTTPError, error.URLError, TimeoutError) as exc:
        raise VoiceDiagnosticError(f'TTS request failed: {exc}') from exc


def transcribe_audio(audio_file):
    if not _voice_diagnostic_is_configured():
        raise VoiceDiagnosticConfigError('Speech-to-text is not configured yet.')

    model = getattr(settings, 'DEEPGRAM_STT_MODEL', 'nova-2')
    if not model:
        raise VoiceDiagnosticConfigError('Speech-to-text is not configured yet.')

    query = parse.urlencode({'model': model, 'smart_format': 'true'})
    url = f'https://api.deepgram.com/v1/listen?{query}'
    audio_file.seek(0)
    payload = audio_file.read()
    content_type = getattr(audio_file, 'content_type', None) or 'audio/webm'
    http_request = request.Request(
        url,
        data=payload,
        method='POST',
        headers={
            'Authorization': f'Token {settings.DEEPGRAM_API_KEY}',
            'Content-Type': content_type,
        },
    )

    try:
        with request.urlopen(http_request, timeout=45) as response:
            response_data = json.loads(response.read().decode('utf-8'))
    except (error.HTTPError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise VoiceDiagnosticError(f'Speech-to-text request failed: {exc}') from exc

    try:
        transcript = response_data['results']['channels'][0]['alternatives'][0]['transcript']
    except (KeyError, IndexError, TypeError) as exc:
        raise VoiceDiagnosticError('Speech-to-text response did not include a transcript.') from exc

    transcript = transcript.strip()
    if not transcript:
        raise VoiceDiagnosticError('Speech-to-text did not detect a clear transcript.')
    return transcript


def _words(text):
    return re.findall(r"[a-z0-9']+", (text or '').lower())


def compare_pronunciation(target_sentence, transcript):
    target_words = _words(target_sentence)
    transcript_words = _words(transcript)
    if not target_words:
        raise VoiceDiagnosticError('target_sentence must be a non-empty string.')

    matcher = SequenceMatcher(a=target_words, b=transcript_words, autojunk=False)
    matched_count = 0
    missing_words = []
    extra_words = []
    substituted_words = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            matched_count += i2 - i1
        elif tag == 'delete':
            missing_words.extend(target_words[i1:i2])
        elif tag == 'insert':
            extra_words.extend(transcript_words[j1:j2])
        elif tag == 'replace':
            missing_words.extend(target_words[i1:i2])
            extra_words.extend(transcript_words[j1:j2])
            substituted_words.extend(
                {
                    'expected': expected,
                    'heard': heard,
                }
                for expected, heard in zip(target_words[i1:i2], transcript_words[j1:j2])
            )

    word_accuracy = round((matched_count / len(target_words)) * 100)
    score = max(0, min(100, word_accuracy))
    if score >= 85:
        feedback = 'Your pronunciation clarity was strong and most words were recognized correctly.'
    elif score >= 60:
        feedback = 'Your pronunciation was understandable, but some words were missed or changed.'
    else:
        feedback = 'Your pronunciation was difficult to recognize. Practice the target sentence slowly and clearly.'

    return {
        'score': score,
        'word_accuracy': word_accuracy,
        'feedback': feedback,
        'missing_words': missing_words,
        'extra_words': extra_words,
        'substituted_words': substituted_words,
    }


def _status_for_score(score):
    if score < 60:
        return 'Needs Review'
    if score < 80:
        return 'Learning'
    return 'Mastered'


def _level_for_score(score):
    if score < 50:
        return 'A1'
    if score < 70:
        return 'A2'
    if score < 85:
        return 'B1'
    return 'B2'


@transaction.atomic
def evaluate_pronunciation(user, audio_file, target_sentence):
    target_sentence = (target_sentence or '').strip()
    if not target_sentence:
        raise VoiceDiagnosticError('target_sentence must be a non-empty string.')
    if audio_file is None:
        raise VoiceDiagnosticError('audio_file is required.')

    transcript = transcribe_audio(audio_file)
    comparison = compare_pronunciation(target_sentence, transcript)
    score = comparison['score']
    status = _status_for_score(score)
    skill, _ = Skill.objects.get_or_create(name='Pronunciation')
    SkillMastery.objects.update_or_create(
        user=user,
        skill=skill,
        defaults={
            'level_code': _level_for_score(score),
            'score': Decimal(score),
            'status': status,
        },
    )

    return {
        'target_sentence': target_sentence,
        'transcript': transcript,
        'score': score,
        'status': status,
        'feedback': comparison['feedback'],
        'word_accuracy': comparison['word_accuracy'],
        'missing_words': comparison['missing_words'],
        'extra_words': comparison['extra_words'],
        'substituted_words': comparison['substituted_words'],
    }
