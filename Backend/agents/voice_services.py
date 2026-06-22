import json
import re
from decimal import Decimal
from difflib import SequenceMatcher
from urllib import error, parse, request

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from learning.models import LearnerProfile, Skill, SkillMastery

from .llm_client import call_llm_json
from .models import VoiceDiagnosticItem, VoiceDiagnosticSession
from .services import VOICE_TEACHER_SESSION_ROUTES, recalculate_learner_level


VOICE_LEVEL_ITEMS = {
    'A1': {
        'pronunciation': [
            'I practice English every day.',
            'My name is Anna.',
            'I live in Cebu.',
        ],
        'listening': [
            {
                'passage': 'My name is Anna. I live in Cebu.',
                'question': 'Where does Anna live?',
                'expected_answer': 'Cebu.',
            },
            {
                'passage': 'I study English every morning.',
                'question': 'When does the speaker study English?',
                'expected_answer': 'Every morning.',
            },
            {
                'passage': 'Maria likes coffee and bread for breakfast.',
                'question': 'What does Maria like for breakfast?',
                'expected_answer': 'Coffee and bread.',
            },
        ],
        'speaking': [
            'Introduce yourself in English.',
            'Describe your daily routine.',
            'What is your learning goal?',
        ],
    },
    'A2': {
        'pronunciation': [
            'I worked on the project yesterday.',
            'Please send me the report today.',
            'I talked to the customer this morning.',
        ],
        'listening': [
            {
                'passage': 'Yesterday, Mark worked on a report.',
                'question': 'What did Mark work on yesterday?',
                'expected_answer': 'A report.',
            },
            {
                'passage': 'He sent the report to his manager before lunch.',
                'question': 'Who did he send the report to?',
                'expected_answer': 'His manager.',
            },
            {
                'passage': 'Anna called the customer because the ticket was urgent.',
                'question': 'Why did Anna call the customer?',
                'expected_answer': 'Because the ticket was urgent.',
            },
        ],
        'speaking': [
            'Describe what you did yesterday.',
            'Talk about something you like and explain why.',
            'Describe your work or school in simple English.',
        ],
    },
    'B1': {
        'pronunciation': [
            'I solved the problem because I checked the network settings.',
            'Although the task was difficult, I finished it on time.',
            'I want to improve my English so I can communicate more clearly.',
        ],
        'listening': [
            {
                'passage': 'The customer could not connect to the internet, so I checked the network settings.',
                'question': 'What problem did the customer have?',
                'expected_answer': 'The customer could not connect to the internet.',
            },
            {
                'passage': 'After restarting the router, the connection worked again.',
                'question': 'What solved the problem?',
                'expected_answer': 'Restarting the router.',
            },
            {
                'passage': 'I documented the issue so the next agent could understand the solution.',
                'question': 'Why did the speaker document the issue?',
                'expected_answer': 'So the next agent could understand the solution.',
            },
        ],
        'speaking': [
            'Describe a problem you solved.',
            'Explain your English learning goal and why it matters.',
            'Give your opinion about using AI to learn English.',
        ],
    },
    'B2': {
        'pronunciation': [
            'The main advantage of this solution is that it reduces support time.',
            'Although both options are useful, I recommend the faster workflow.',
            'We should review the process before making a final decision.',
        ],
        'listening': [
            {
                'passage': 'The faster workflow saves time, but it requires more careful review.',
                'question': 'What is the advantage of the faster workflow?',
                'expected_answer': 'It saves time.',
            },
            {
                'passage': 'The slower workflow takes longer, but it reduces mistakes during support handoffs.',
                'question': 'What is the advantage of the slower workflow?',
                'expected_answer': 'It reduces mistakes.',
            },
            {
                'passage': 'The tradeoff is speed versus accuracy.',
                'question': 'What tradeoff is described?',
                'expected_answer': 'Speed versus accuracy.',
            },
        ],
        'speaking': [
            'Explain a workplace or technical process that you know well.',
            'Compare two ways to improve English speaking skills.',
            'Explain the advantages and disadvantages of learning with AI.',
        ],
    },
    'C1': {
        'pronunciation': [
            'From my perspective, the most effective solution requires both accuracy and speed.',
            'The challenge is not only technical but also related to communication.',
            'I would recommend a structured approach that balances quality and efficiency.',
        ],
        'listening': [
            {
                'passage': 'The team should improve response time, but speed should not reduce accuracy.',
                'question': 'What should the team improve?',
                'expected_answer': 'Response time.',
            },
            {
                'passage': 'A structured workflow can help agents solve issues faster while keeping quality consistent.',
                'question': 'What solution is recommended?',
                'expected_answer': 'A structured workflow.',
            },
            {
                'passage': 'The goal is to balance efficiency with reliable support outcomes.',
                'question': 'What should be balanced?',
                'expected_answer': 'Efficiency and reliable support outcomes.',
            },
        ],
        'speaking': [
            'Present a structured recommendation for improving communication at work.',
            'Defend your opinion about whether AI can replace human teachers.',
            'Summarize a complex problem and explain a practical solution.',
        ],
    },
    'C2': {
        'pronunciation': [
            'A thoughtful decision requires careful analysis, practical judgment, and clear communication.',
            'The proposal is compelling, but its long-term implications require further evaluation.',
            'Effective leadership depends on clarity, empathy, and strategic execution.',
        ],
        'listening': [
            {
                'passage': 'Effective support is not only about solving issues quickly.',
                'question': 'What is effective support not only about?',
                'expected_answer': 'Solving issues quickly.',
            },
            {
                'passage': 'It also requires judgment, empathy, and the ability to explain complex solutions clearly.',
                'question': 'What qualities does effective support require?',
                'expected_answer': 'Judgment, empathy, and clear explanation.',
            },
            {
                'passage': "A strong agent adapts explanations to the user's technical level without losing accuracy.",
                'question': "What does a strong agent adapt?",
                'expected_answer': "Explanations to the user's technical level.",
            },
        ],
        'speaking': [
            'Give a nuanced argument about the future of AI-assisted education.',
            'Explain how communication style should change depending on audience expertise.',
            'Present a persuasive professional recommendation with clear tradeoffs.',
        ],
    },
}

VOICE_DIAGNOSTIC_SKILL_CONFIG = {
    'pronunciation': {
        'label': VoiceDiagnosticItem.SKILL_PRONUNCIATION,
        'session_field': 'pronunciation_score',
        'task_type': 'repeat_sentence',
    },
    'listening': {
        'label': VoiceDiagnosticItem.SKILL_LISTENING,
        'session_field': 'listening_score',
        'task_type': 'listening_comprehension',
    },
    'speaking': {
        'label': VoiceDiagnosticItem.SKILL_SPEAKING,
        'session_field': 'speaking_score',
        'task_type': 'speaking_response',
    },
}

VOICE_DIAGNOSTIC_RECOMMENDED_FOCUS_ORDER = (
    VoiceDiagnosticItem.SKILL_PRONUNCIATION,
    VoiceDiagnosticItem.SKILL_LISTENING,
    VoiceDiagnosticItem.SKILL_SPEAKING,
)
CEFR_LEVEL_ORDER = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
VOICE_TEXT_STOPWORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'because', 'but', 'by', 'for',
    'from', 'had', 'has', 'have', 'he', 'her', 'his', 'i', 'in', 'is', 'it',
    'me', 'my', 'of', 'on', 'our', 'she', 'so', 'that', 'the', 'their', 'them',
    'they', 'this', 'to', 'was', 'we', 'were', 'with', 'you', 'your',
}
LISTENING_STOPWORDS = VOICE_TEXT_STOPWORDS | {
    'can', 'could', 'did', 'does', 'do', 'what', 'when', 'where', 'who', 'why',
    'how', 'before', 'after', 'again', 'anna', 'maria', 'mark', 'speaker',
}
QUESTION_STOPWORDS = LISTENING_STOPWORDS | {
    'describe', 'explain', 'tell', 'talk', 'give', 'about',
}
SPEAKING_FILLER_PATTERNS = (
    r'\bum\b',
    r'\buh\b',
    r'\blike\b',
    r'\byou know\b',
    r'\bactually\b',
    r'\bbasically\b',
)
CANONICAL_WORD_MAP = {
    'answers': 'answer',
    'answered': 'answer',
    'answering': 'answer',
    'connected': 'connect',
    'connecting': 'connect',
    'connection': 'connect',
    'connections': 'connect',
    'customer': 'customer',
    'customers': 'customer',
    'described': 'describe',
    'describing': 'describe',
    'details': 'detail',
    'documented': 'document',
    'documenting': 'document',
    'faster': 'fast',
    'fluently': 'fluent',
    'improving': 'improve',
    'internet': 'internet',
    'issue': 'issue',
    'issues': 'issue',
    'mistakes': 'mistake',
    'networking': 'network',
    'no': 'not',
    'online': 'internet',
    'practicing': 'practice',
    'problems': 'problem',
    'reasons': 'reason',
    'restarted': 'restart',
    'restarting': 'restart',
    'responses': 'response',
    'router': 'router',
    'routers': 'router',
    'slower': 'slow',
    'solved': 'solve',
    'solving': 'solve',
    'speaking': 'speak',
    'studying': 'study',
    'teacher': 'teacher',
    'teachers': 'teacher',
    'understood': 'understand',
    'understanding': 'understand',
    'wifi': 'internet',
    'worked': 'work',
    'working': 'work',
}


class VoiceDiagnosticError(Exception):
    pass


class VoiceDiagnosticConfigError(VoiceDiagnosticError):
    pass


def _normalized_level(level_code, default='A1'):
    normalized = (level_code or '').strip().upper()
    if normalized not in VOICE_LEVEL_ITEMS:
        return default
    return normalized


def _voice_level_for_user(user):
    profile_level = (
        LearnerProfile.objects.filter(user=user)
        .values_list('current_level', flat=True)
        .first()
    )
    return _normalized_level(profile_level, default='A1')


def _build_prompt_payload(level_code):
    level_items = VOICE_LEVEL_ITEMS[level_code]
    pronunciation_items = [
        {
            'item_number': index + 1,
            'target_sentence': sentence,
        }
        for index, sentence in enumerate(level_items['pronunciation'])
    ]
    listening_items = [
        {
            'item_number': index + 1,
            'passage': item['passage'],
            'question': item['question'],
            'expected_answer': item['expected_answer'],
        }
        for index, item in enumerate(level_items['listening'])
    ]
    speaking_items = [
        {
            'item_number': index + 1,
            'question': question,
        }
        for index, question in enumerate(level_items['speaking'])
    ]
    return {
        'level_code': level_code,
        'pronunciation': {
            'target_sentence': pronunciation_items[0]['target_sentence'],
            'items': pronunciation_items,
        },
        'listening': {
            'passage': listening_items[0]['passage'],
            'question': listening_items[0]['question'],
            'expected_answer': listening_items[0]['expected_answer'],
            'items': listening_items,
        },
        'speaking': {
            'question': speaking_items[0]['question'],
            'items': speaking_items,
        },
    }


def get_voice_diagnostic_prompts(user=None):
    level_code = _voice_level_for_user(user) if user is not None else 'A1'
    return _build_prompt_payload(level_code)


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


def _resolve_transcript(audio_file=None, transcript=None):
    transcript = (transcript or '').strip()
    if transcript:
        return transcript
    if audio_file is None:
        raise VoiceDiagnosticError('audio_file or transcript is required.')
    return transcribe_audio(audio_file)


def _resolve_batch_transcript(item):
    audio_file = item.get('audio_file')
    if audio_file is not None:
        return _resolve_transcript(audio_file=audio_file, transcript=item.get('transcript'))
    if 'transcript' in item:
        return (item.get('transcript') or '').strip()
    raise VoiceDiagnosticError('audio_file or transcript is required.')


def _words(text):
    return re.findall(r"[a-z0-9']+", (text or '').lower())


def _clamp_score(value):
    return max(0, min(100, round(value)))


def _ratio_percent(numerator, denominator):
    if denominator <= 0:
        return 0
    return _clamp_score((numerator / denominator) * 100)


def _weighted_score(weighted_parts):
    return _clamp_score(
        sum(score * weight for score, weight in weighted_parts)
    )


def _canonicalize_word(word):
    normalized = (word or '').lower().strip()
    if not normalized:
        return normalized
    if normalized in CANONICAL_WORD_MAP:
        return CANONICAL_WORD_MAP[normalized]
    if normalized.endswith('ies') and len(normalized) > 4:
        return normalized[:-3] + 'y'
    if normalized.endswith('ing') and len(normalized) > 5:
        return normalized[:-3]
    if normalized.endswith('ed') and len(normalized) > 4:
        return normalized[:-2]
    if normalized.endswith('es') and len(normalized) > 4:
        return normalized[:-2]
    if normalized.endswith('s') and len(normalized) > 3:
        return normalized[:-1]
    return normalized


def _canonical_tokens(text, stopwords=None):
    tokens = []
    for word in _words(text):
        canonical = _canonicalize_word(word)
        if not canonical:
            continue
        if stopwords and canonical in stopwords:
            continue
        tokens.append(canonical)
    return tokens


def _unique_in_order(values):
    seen = set()
    unique_values = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values


def _sentence_count(text):
    sentences = [
        sentence.strip()
        for sentence in re.split(r'[.!?]+', text or '')
        if sentence.strip()
    ]
    if sentences:
        return len(sentences)
    return 1 if _words(text) else 0


def _count_filler_words(text):
    lowered = (text or '').lower()
    return sum(
        len(re.findall(pattern, lowered))
        for pattern in SPEAKING_FILLER_PATTERNS
    )


def _repetition_penalty(tokens):
    if not tokens:
        return 0
    most_common_count = max(tokens.count(token) for token in set(tokens))
    repeated_ratio = 1 - (len(set(tokens)) / len(tokens))
    penalty = max(0, most_common_count - 2) * 6
    penalty += round(repeated_ratio * 20)
    return penalty


def _expected_keyword_data(expected_answer):
    expected_keywords = _unique_in_order(
        _canonical_tokens(expected_answer, stopwords=LISTENING_STOPWORDS)
    )
    if not expected_keywords:
        raise VoiceDiagnosticError('expected_answer must be a non-empty string.')
    return expected_keywords


def _question_keyword_data(question):
    return set(_canonical_tokens(question, stopwords=QUESTION_STOPWORDS))


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

    word_accuracy = _ratio_percent(matched_count, len(target_words))
    target_completion = _ratio_percent(
        min(len(transcript_words), len(target_words)),
        len(target_words),
    )
    sequence_accuracy = _clamp_score(matcher.ratio() * 100)
    substitution_control = (
        0 if not transcript_words
        else _clamp_score(100 - ((len(substituted_words) / len(target_words)) * 100))
    )
    missing_word_control = _clamp_score(
        100 - ((len(missing_words) / len(target_words)) * 100)
    )
    extra_word_control = _clamp_score(
        100 - ((len(extra_words) / max(1, len(target_words))) * 100)
    )
    clarity_estimate = _clamp_score(
        (word_accuracy * 0.65)
        + (sequence_accuracy * 0.25)
        + (extra_word_control * 0.10)
    )
    score = _weighted_score(
        (
            (word_accuracy, 0.35),
            (target_completion, 0.20),
            (sequence_accuracy, 0.15),
            (substitution_control, 0.10),
            (missing_word_control, 0.10),
            (extra_word_control, 0.05),
            (clarity_estimate, 0.05),
        )
    )

    if not transcript_words:
        score = min(score, 15)
    elif matched_count == 0:
        score = min(score, 35)
    elif word_accuracy < 40 and sequence_accuracy < 45:
        score = min(score, 55)

    score_reasons = []
    if matched_count:
        score_reasons.append(
            f'Most target words were recognized at {word_accuracy}% word accuracy.'
        )
    else:
        score_reasons.append('The transcript did not capture the target sentence clearly.')
    if substituted_words:
        score_reasons.append(
            f'{len(substituted_words)} substituted word'
            f'{"s" if len(substituted_words) != 1 else ""} reduced the score.'
        )
    if missing_words:
        score_reasons.append(
            f'{len(missing_words)} target word'
            f'{"s were" if len(missing_words) != 1 else " was"} missing.'
        )
    if extra_words:
        score_reasons.append(
            f'{len(extra_words)} extra word'
            f'{"s made" if len(extra_words) != 1 else " made"} the repetition less precise.'
        )
    if not transcript_words:
        score_reasons = ['No clear transcript was available for this repetition item.']

    if score >= 90 and not missing_words and not extra_words and not substituted_words:
        feedback = 'Excellent repetition. All target words were captured clearly.'
    elif score >= 80:
        feedback = 'Good attempt. Most words were clear, but one or two details reduced the score.'
    elif missing_words:
        feedback = 'You said part of the sentence clearly, but some target words were missing.'
    else:
        feedback = (
            'The transcript does not closely match the target sentence. '
            'Try repeating the full sentence slowly first.'
        )

    explanation = (
        f'Matched {matched_count} of {len(target_words)} target words with '
        f'{len(substituted_words)} substitutions, {len(missing_words)} missing words, '
        f'and {len(extra_words)} extra words.'
    )
    breakdown = {
        'rubric': 'pronunciation_v2',
        'word_accuracy': word_accuracy,
        'target_completion': target_completion,
        'sequence_accuracy': sequence_accuracy,
        'substitution_control': substitution_control,
        'missing_word_control': missing_word_control,
        'extra_word_control': extra_word_control,
        'clarity_estimate': clarity_estimate,
        'missing_words': missing_words,
        'extra_words': extra_words,
        'substituted_words': substituted_words,
        'score_reasons': score_reasons,
    }
    return {
        'score': score,
        'feedback': feedback,
        'explanation': explanation,
        'word_accuracy': word_accuracy,
        'missing_words': missing_words,
        'extra_words': extra_words,
        'substituted_words': substituted_words,
        'breakdown': breakdown,
    }


def _normalize_score(raw_score):
    if not isinstance(raw_score, (int, float)):
        return None
    return max(0, min(100, round(raw_score)))


def _evaluate_listening_with_llm(question, expected_answer, user_answer):
    if not getattr(settings, 'USE_LLM_VOICE_DIAGNOSTIC_ENHANCEMENT', False):
        return None
    system_prompt = (
        'You are an English listening comprehension evaluator. Return only JSON '
        'with semantic_match and feedback. semantic_match must be an integer from '
        '0 to 100 based on whether the learner answer captures the expected meaning. '
        'Keep the feedback concise and factual.'
    )
    user_prompt = (
        f'Question: {question}\n'
        f'Expected answer: {expected_answer}\n'
        f'Learner answer: {user_answer}'
    )
    payload = call_llm_json(system_prompt, user_prompt)
    if not isinstance(payload, dict):
        return None

    score = _normalize_score(payload.get('semantic_match'))
    feedback = payload.get('feedback')
    if score is None or not isinstance(feedback, str) or not feedback.strip():
        return None
    return score, feedback.strip()


def _listening_keyword_details(expected_answer, user_answer):
    expected_keywords = _expected_keyword_data(expected_answer)
    user_keywords = _unique_in_order(
        _canonical_tokens(user_answer, stopwords=LISTENING_STOPWORDS)
    )
    matched_keywords = [word for word in expected_keywords if word in user_keywords]
    missing_keywords = [word for word in expected_keywords if word not in user_keywords]
    ratio = len(matched_keywords) / len(expected_keywords)

    if ratio >= 0.85:
        answer_match = 'complete'
    elif ratio >= 0.5:
        answer_match = 'partial'
    elif matched_keywords:
        answer_match = 'minimal'
    else:
        answer_match = 'minimal' if user_keywords else 'none'

    return matched_keywords, missing_keywords, answer_match, ratio


def _listening_similarity(expected_answer, user_answer):
    expected_tokens = _expected_keyword_data(expected_answer)
    user_tokens = _unique_in_order(
        _canonical_tokens(user_answer, stopwords=LISTENING_STOPWORDS)
    )
    if not user_tokens:
        return 0
    expected_set = set(expected_tokens)
    user_set = set(user_tokens)
    overlap = len(expected_set & user_set)
    recall = overlap / len(expected_set)
    precision = overlap / max(1, len(user_set))
    sequence_ratio = SequenceMatcher(
        a=' '.join(expected_tokens),
        b=' '.join(user_tokens),
        autojunk=False,
    ).ratio()
    return _clamp_score(
        ((recall * 0.60) + (precision * 0.20) + (sequence_ratio * 0.20)) * 100
    )


def _listening_clarity_score(user_answer):
    user_tokens = _canonical_tokens(user_answer, stopwords=LISTENING_STOPWORDS)
    if not user_tokens:
        return 0
    penalty = _repetition_penalty(user_tokens)
    if len(user_tokens) > 18:
        penalty += min((len(user_tokens) - 18) * 2, 20)
    return _clamp_score(92 - penalty)


def _evaluate_listening_rule_based(question, expected_answer, user_answer):
    matched_keywords, missing_keywords, answer_match, keyword_ratio = _listening_keyword_details(
        expected_answer,
        user_answer,
    )
    question_keywords = _question_keyword_data(question)
    user_keywords = set(_canonical_tokens(user_answer, stopwords=LISTENING_STOPWORDS))
    semantic_match = _listening_similarity(expected_answer, user_answer)
    content_word_count = len(_canonical_tokens(user_answer, stopwords=LISTENING_STOPWORDS))
    overlap_with_prompt = len(
        user_keywords & (set(_expected_keyword_data(expected_answer)) | question_keywords)
    )
    question_relevance = _clamp_score(
        (keyword_ratio * 65 * 100 / 100)
        + (
            (overlap_with_prompt / max(1, min(4, len(question_keywords) or 1)))
            * 35
        )
    )
    completeness = _clamp_score(
        (keyword_ratio * 65)
        + (
            min(content_word_count, max(2, len(_expected_keyword_data(expected_answer)) + 1))
            / max(2, len(_expected_keyword_data(expected_answer)) + 1)
        ) * 35
    )
    correct_detail = _clamp_score((keyword_ratio * 75) + (semantic_match * 0.25))
    clarity = _listening_clarity_score(user_answer)

    llm_feedback = _evaluate_listening_with_llm(question, expected_answer, user_answer)
    if llm_feedback is not None:
        llm_semantic_match, _ = llm_feedback
        if abs(llm_semantic_match - semantic_match) <= 15:
            semantic_match = _clamp_score((semantic_match * 0.8) + (llm_semantic_match * 0.2))

    score = _weighted_score(
        (
            (correct_detail, 0.40),
            (question_relevance, 0.25),
            (completeness, 0.20),
            (semantic_match, 0.10),
            (clarity, 0.05),
        )
    )
    if not user_keywords:
        score = min(score, 15)
    elif keyword_ratio == 0 and semantic_match < 35:
        score = min(score, 35)
    elif question_relevance < 45 and completeness < 50:
        score = min(score, 59)

    score_reasons = []
    if answer_match == 'complete':
        score_reasons.append('The answer included the main expected detail.')
    elif answer_match == 'partial':
        score_reasons.append('The answer captured part of the expected detail.')
    elif user_keywords:
        score_reasons.append('The answer included limited useful detail from the passage.')
    else:
        score_reasons.append('No clear answer was provided for this listening item.')

    if overlap_with_prompt:
        score_reasons.append('The answer stayed relevant to the listening question.')
    else:
        score_reasons.append('The answer did not stay close to the listening question.')

    if score >= 90:
        feedback = 'Correct. You understood the key detail from the passage.'
    elif score >= 80:
        feedback = 'Mostly correct. You understood the main point, with only a small detail to improve.'
    elif score >= 60:
        feedback = 'You understood part of the answer, but one important detail is missing.'
    elif score >= 45:
        feedback = 'Your answer is relevant, but it is too vague to show full understanding.'
    else:
        feedback = 'Your answer does not match the information in the passage. Listen again for the main detail.'

    breakdown = {
        'rubric': 'listening_v2',
        'correct_detail': correct_detail,
        'question_relevance': question_relevance,
        'completeness': completeness,
        'semantic_match': semantic_match,
        'clarity': clarity,
        'matched_keywords': matched_keywords,
        'missing_keywords': missing_keywords,
        'answer_match': answer_match,
        'score_reasons': score_reasons,
    }
    explanation = ' '.join(score_reasons)
    return {
        'score': score,
        'feedback': feedback,
        'explanation': explanation,
        'matched_keywords': matched_keywords,
        'missing_keywords': missing_keywords,
        'answer_match': answer_match,
        'breakdown': breakdown,
    }


def _evaluate_speaking_transcript(question, transcript):
    transcript_words = _words(transcript)
    canonical_words = _canonical_tokens(transcript, stopwords=None)
    content_words = _canonical_tokens(transcript, stopwords=VOICE_TEXT_STOPWORDS)
    word_count = len(transcript_words)
    sentence_count = _sentence_count(transcript)
    filler_count = _count_filler_words(transcript)
    unique_content_words = len(set(content_words))
    repetition_penalty = _repetition_penalty(content_words or canonical_words)

    prompt_terms = set(_canonical_tokens(question, stopwords=QUESTION_STOPWORDS))
    question_lower = (question or '').lower()
    if 'introduce yourself' in question_lower or 'tell me about yourself' in question_lower:
        prompt_terms |= {'name', 'work', 'english', 'improve'}
    if 'daily routine' in question_lower:
        prompt_terms |= {'day', 'morning', 'usually', 'work', 'study'}
    if 'learning goal' in question_lower or 'improve your english' in question_lower:
        prompt_terms |= {'goal', 'improve', 'english', 'work', 'communication'}
    if 'problem' in question_lower and 'solved' in question_lower:
        prompt_terms |= {'problem', 'solve', 'issue', 'fix', 'because'}
    if 'opinion' in question_lower or 'advantages' in question_lower or 'disadvantages' in question_lower:
        prompt_terms |= {'think', 'because', 'advantage', 'disadvantage', 'recommend'}

    overlap_count = len(set(content_words) & prompt_terms)
    first_person_present = bool(re.search(r"\b(i|my|me|i'm)\b", transcript, flags=re.IGNORECASE))
    connector_count = len(
        re.findall(r'\b(because|so|and|but|however|although|also|then)\b', transcript, flags=re.IGNORECASE)
    )
    grammar_pattern_count = sum(
        1
        for pattern in (
            r"\bmy name is\b",
            r"\bi am\b",
            r"\bi'm\b",
            r"\bi want\b",
            r"\bi work\b",
            r"\bi study\b",
            r"\bi like\b",
            r"\bi need\b",
            r"\bi improve\b",
        )
        if re.search(pattern, transcript, flags=re.IGNORECASE)
    )

    task_relevance = _clamp_score(
        min(70, overlap_count * 18)
        + (20 if first_person_present else 0)
        + (10 if connector_count else 0)
    )
    completeness = _clamp_score(
        min(65, word_count * 3)
        + min(20, max(0, sentence_count - 1) * 10)
        + min(15, overlap_count * 5)
    )
    clarity = _clamp_score(
        78
        + min(12, sentence_count * 4)
        - min(24, filler_count * 6)
        - min(20, repetition_penalty)
    )
    grammar_control = _clamp_score(
        42
        + min(28, grammar_pattern_count * 10)
        + min(15, connector_count * 5)
        - min(20, filler_count * 4)
    )
    vocabulary_range = _clamp_score(min(100, unique_content_words * 11))
    coherence = _clamp_score(
        40
        + min(20, overlap_count * 6)
        + min(20, connector_count * 8)
        + min(20, sentence_count * 6)
        - min(20, repetition_penalty)
    )
    fluency_signal = _clamp_score(
        88
        - min(40, filler_count * 10)
        - min(24, repetition_penalty)
    )
    score = _weighted_score(
        (
            (task_relevance, 0.25),
            (completeness, 0.20),
            (clarity, 0.15),
            (grammar_control, 0.15),
            (vocabulary_range, 0.10),
            (coherence, 0.10),
            (fluency_signal, 0.05),
        )
    )
    if word_count == 0:
        score = min(score, 15)
    elif task_relevance < 25:
        score = min(score, 39)
    elif word_count < 5:
        score = min(score, 59)
    elif filler_count >= 4 and filler_count >= max(3, word_count // 4):
        score = min(score, 69)

    strengths = []
    improvement_areas = []
    score_reasons = []
    if task_relevance >= 75:
        strengths.append('The answer directly addressed the prompt.')
        score_reasons.append('The answer was relevant to the speaking task.')
    else:
        improvement_areas.append('Stay closer to the main prompt with one clear idea.')
        score_reasons.append('Task relevance was limited, which reduced the score.')
    if completeness >= 70:
        strengths.append('The response included a clear main idea.')
        score_reasons.append('The response included enough supporting detail.')
    else:
        improvement_areas.append('Add one more supporting detail.')
    if grammar_control >= 70:
        strengths.append('Grammar control was understandable across the answer.')
    else:
        improvement_areas.append('Use complete sentences with clearer grammar.')
    if filler_count >= 3:
        improvement_areas.append('Reduce filler words.')
        score_reasons.append('Frequent filler words reduced the fluency signal.')
    if not strengths:
        strengths.append('You completed the speaking attempt.')
    if not improvement_areas:
        improvement_areas.append('Keep practicing to make your speaking even more natural and detailed.')

    if score >= 85:
        feedback = 'Strong answer. You answered the prompt clearly and gave enough detail.'
    elif score >= 75:
        feedback = 'Clear answer. You answered the prompt well, with a little room for more detail.'
    elif score >= 60:
        feedback = 'Your answer is relevant, but it needs more detail to show stronger speaking control.'
    elif score >= 40:
        feedback = 'Your answer is very short or incomplete. Add a clearer main idea and more detail.'
    else:
        feedback = (
            'Your answer is difficult to understand or does not fully answer the prompt. '
            'Try using complete sentences and one clear main idea.'
        )

    breakdown = {
        'rubric': 'speaking_v2',
        'task_relevance': task_relevance,
        'completeness': completeness,
        'clarity': clarity,
        'grammar_control': grammar_control,
        'vocabulary_range': vocabulary_range,
        'coherence': coherence,
        'fluency_signal': fluency_signal,
        'word_count': word_count,
        'sentence_count': sentence_count,
        'filler_count': filler_count,
        'strengths': strengths,
        'improvement_areas': improvement_areas,
        'score_reasons': score_reasons,
    }
    return {
        'score': score,
        'feedback': feedback,
        'explanation': ' '.join(score_reasons),
        'strengths': strengths,
        'improvement_areas': improvement_areas,
        'breakdown': breakdown,
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


def _update_skill_mastery(user, skill_name, score):
    status = _status_for_score(score)
    skill, _ = Skill.objects.get_or_create(name=skill_name)
    SkillMastery.objects.update_or_create(
        user=user,
        skill=skill,
        defaults={
            'level_code': _level_for_score(score),
            'score': Decimal(score),
            'status': status,
        },
    )
    recalculate_learner_level(user)
    return status


def _pronunciation_summary(score):
    if score >= 85:
        return 'Your pronunciation was clear across most target sentences.'
    if score >= 60:
        return 'Your pronunciation was understandable across the assessment, but several words still need practice.'
    return 'Your pronunciation needs more work across the target sentences. Practice slowly and clearly.'


def _listening_summary(score):
    if score >= 85:
        return 'You understood the key details in most listening items.'
    if score >= 60:
        return 'You understood some important listening details, but you missed part of the assessment.'
    return 'You need more listening practice to catch the key details consistently.'


def _speaking_summary(score):
    if score >= 85:
        return 'Your spoken answers were clear, relevant, and mostly complete.'
    if score >= 60:
        return 'Your spoken answers were understandable, but they need stronger detail and fluency.'
    return 'Your spoken answers need clearer structure, more detail, and stronger relevance.'


def _aggregation_consistency_note(aggregation):
    if aggregation['consistency_adjustment'] < 0:
        return 'Your score was adjusted slightly because item performance was inconsistent.'
    return ''


def _skill_feedback_summary(skill_key, score, aggregation):
    if skill_key == 'pronunciation':
        summary = _pronunciation_summary(score)
    elif skill_key == 'listening':
        summary = _listening_summary(score)
    else:
        summary = _speaking_summary(score)

    consistency_note = _aggregation_consistency_note(aggregation)
    if consistency_note:
        return f'{summary} {consistency_note}'
    return summary


def _aggregate_batch_scores(item_results):
    item_scores = [item['score'] for item in item_results]
    base_average = round(sum(item_scores) / len(item_scores))
    score_range = max(item_scores) - min(item_scores)
    if score_range >= 40:
        consistency_adjustment = -5
    elif score_range >= 30:
        consistency_adjustment = -3
    else:
        consistency_adjustment = 0
    final_score = _clamp_score(base_average + consistency_adjustment)
    return final_score, {
        'base_average': base_average,
        'score_range': score_range,
        'consistency_adjustment': consistency_adjustment,
        'final_score': final_score,
    }


def _voice_diagnostic_score_map(session):
    return {
        VoiceDiagnosticItem.SKILL_PRONUNCIATION: (
            int(session.pronunciation_score)
            if session.pronunciation_score is not None else None
        ),
        VoiceDiagnosticItem.SKILL_LISTENING: (
            int(session.listening_score)
            if session.listening_score is not None else None
        ),
        VoiceDiagnosticItem.SKILL_SPEAKING: (
            int(session.speaking_score)
            if session.speaking_score is not None else None
        ),
    }


def _voice_diagnostic_summary(recommended_focus, score_map):
    if recommended_focus is None:
        return ''
    if all(score is not None and score >= 80 for score in score_map.values()):
        return (
            'Your voice skills are strong. Continue balanced practice or focus '
            'on the lowest score for refinement.'
        )
    return (
        f'{recommended_focus} is your recommended focus. Practice with the '
        f'{recommended_focus} Teacher Session, then retake the Voice Diagnostic later.'
    )


def _voice_diagnostic_recommended_focus(score_map):
    scored_skills = [
        (skill_name, score_map.get(skill_name))
        for skill_name in VOICE_DIAGNOSTIC_RECOMMENDED_FOCUS_ORDER
        if score_map.get(skill_name) is not None
    ]
    if len(scored_skills) != len(VOICE_DIAGNOSTIC_RECOMMENDED_FOCUS_ORDER):
        return None
    scored_skills.sort(key=lambda item: item[1])
    return scored_skills[0][0]


def build_voice_recommended_focus_reason(skill_name, scores):
    if not skill_name:
        return ''
    if all(score is not None and score >= 80 for score in scores.values()):
        return (
            'Your voice skills are strong. Continue balanced practice or focus '
            'on the lowest score for refinement.'
        )
    return f'{skill_name} is your lowest voice skill based on this official diagnostic.'


def get_next_teacher_session_for_focus(skill_name):
    href = VOICE_TEACHER_SESSION_ROUTES.get(skill_name)
    if not href:
        return None
    return {
        'skill': skill_name,
        'label': f'Start {skill_name} Teacher Session',
        'href': href,
    }


def _voice_diagnostic_session_metadata(session):
    metadata = session.metadata if isinstance(session.metadata, dict) else {}
    skill_results = metadata.get('skill_results')
    if not isinstance(skill_results, dict):
        skill_results = {}
    metadata['skill_results'] = skill_results
    return metadata, skill_results


def start_voice_diagnostic_session(user):
    return VoiceDiagnosticSession.objects.create(user=user)


def get_voice_diagnostic_session(user, session_id):
    session = (
        VoiceDiagnosticSession.objects.filter(user=user, pk=session_id)
        .prefetch_related('items')
        .first()
    )
    if session is None:
        raise VoiceDiagnosticError('Voice diagnostic session not found.')
    return session


def _get_or_create_voice_diagnostic_session(user, session_id=None):
    if session_id is not None:
        session = get_voice_diagnostic_session(user, session_id)
        if session.status == VoiceDiagnosticSession.STATUS_COMPLETED:
            raise VoiceDiagnosticError(
                'Voice diagnostic session is already completed. Start a new session.'
            )
        return session

    existing_session = (
        VoiceDiagnosticSession.objects.filter(
            user=user,
            status=VoiceDiagnosticSession.STATUS_IN_PROGRESS,
        )
        .order_by('-started_at', '-id')
        .first()
    )
    if existing_session is not None:
        return existing_session
    return start_voice_diagnostic_session(user)


def _voice_diagnostic_item_defaults(skill_key, item_result):
    if skill_key == 'pronunciation':
        return {
            'task_type': VOICE_DIAGNOSTIC_SKILL_CONFIG[skill_key]['task_type'],
            'prompt_text': item_result['target_sentence'],
            'target_text': item_result['target_sentence'],
            'transcript': item_result['transcript'],
            'score': Decimal(item_result['score']),
            'feedback': item_result['feedback'],
            'details': item_result['breakdown'],
        }
    if skill_key == 'listening':
        return {
            'task_type': VOICE_DIAGNOSTIC_SKILL_CONFIG[skill_key]['task_type'],
            'prompt_text': item_result['question'],
            'passage_text': item_result.get('passage', ''),
            'question_text': item_result['question'],
            'expected_answer': item_result['expected_answer'],
            'user_answer': item_result['user_answer'],
            'score': Decimal(item_result['score']),
            'feedback': item_result['feedback'],
            'details': item_result['breakdown'],
        }
    return {
        'task_type': VOICE_DIAGNOSTIC_SKILL_CONFIG[skill_key]['task_type'],
        'prompt_text': item_result['question'],
        'question_text': item_result['question'],
        'user_answer': item_result['transcript'],
        'transcript': item_result['transcript'],
        'score': Decimal(item_result['score']),
        'feedback': item_result['feedback'],
        'details': item_result['breakdown'],
    }


def _finalize_voice_diagnostic_session(session):
    score_map = _voice_diagnostic_score_map(session)
    recommended_focus = _voice_diagnostic_recommended_focus(score_map)
    if recommended_focus is None:
        session.status = VoiceDiagnosticSession.STATUS_IN_PROGRESS
        session.recommended_focus = ''
        session.summary = ''
        session.completed_at = None
        return

    session.status = VoiceDiagnosticSession.STATUS_COMPLETED
    session.recommended_focus = recommended_focus
    session.summary = _voice_diagnostic_summary(recommended_focus, score_map)
    session.completed_at = timezone.now()


def _persist_voice_diagnostic_batch(user, skill_key, batch_result, session_id=None):
    session = _get_or_create_voice_diagnostic_session(user, session_id=session_id)
    config = VOICE_DIAGNOSTIC_SKILL_CONFIG[skill_key]

    for item_result in batch_result['items']:
        VoiceDiagnosticItem.objects.update_or_create(
            session=session,
            skill=config['label'],
            item_number=item_result['item_number'],
            defaults=_voice_diagnostic_item_defaults(skill_key, item_result),
        )

    setattr(session, config['session_field'], Decimal(batch_result['final_score']))
    metadata, skill_results = _voice_diagnostic_session_metadata(session)
    skill_results[skill_key] = {
        'final_score': batch_result['final_score'],
        'status': batch_result['status'],
        'level_code': batch_result['level_code'],
        'item_count': len(batch_result['items']),
        'aggregation': batch_result.get('aggregation', {}),
    }
    session.metadata = metadata
    _finalize_voice_diagnostic_session(session)
    session.save()
    return session


def serialize_voice_diagnostic_session_state(session):
    return {
        'session_id': session.id,
        'session_status': session.status,
        'recommended_focus': session.recommended_focus,
        'summary': session.summary,
        'started_at': session.started_at.isoformat().replace('+00:00', 'Z'),
        'completed_at': (
            session.completed_at.isoformat().replace('+00:00', 'Z')
            if session.completed_at else None
        ),
    }


def build_voice_diagnostic_report(session):
    score_map = _voice_diagnostic_score_map(session)
    if (
        session.status != VoiceDiagnosticSession.STATUS_COMPLETED
        or any(score is None for score in score_map.values())
    ):
        return {
            'session_id': session.id,
            'status': session.status,
            'official_mastery_updated': False,
            'message': 'Complete all voice diagnostic sections to view your final report.',
        }

    recommended_focus = (
        session.recommended_focus
        or _voice_diagnostic_recommended_focus(score_map)
    )
    recommended_focus_reason = build_voice_recommended_focus_reason(
        recommended_focus,
        score_map,
    )
    next_teacher_session = get_next_teacher_session_for_focus(recommended_focus)
    skill_breakdown = []
    items_by_skill = {
        skill_name: []
        for skill_name in VOICE_DIAGNOSTIC_RECOMMENDED_FOCUS_ORDER
    }
    for item in session.items.all():
        items_by_skill.setdefault(item.skill, []).append(item)

    for skill_name in VOICE_DIAGNOSTIC_RECOMMENDED_FOCUS_ORDER:
        item_scores = [
            int(item.score)
            for item in sorted(items_by_skill.get(skill_name, []), key=lambda entry: entry.item_number)
            if item.score is not None
        ]
        skill_breakdown.append(
            {
                'skill': skill_name,
                'final_score': score_map.get(skill_name),
                'item_scores': item_scores,
                'item_count': len(item_scores),
            }
        )

    return {
        'session_id': session.id,
        'status': session.status,
        'official_mastery_updated': True,
        'scores': score_map,
        'skill_breakdown': skill_breakdown,
        'recommended_focus': recommended_focus,
        'recommended_focus_reason': recommended_focus_reason,
        'next_teacher_session': next_teacher_session,
        'recommendation_href': '/recommendation',
        'study_plan_href': '/study-plan?refresh=1',
        'history_href': '/voice-diagnostic/history',
        'dashboard_href': '/dashboard',
        'summary': _voice_diagnostic_summary(recommended_focus, score_map),
    }


def _build_pronunciation_result(target_sentence, transcript):
    target_sentence = (target_sentence or '').strip()
    transcript = (transcript or '').strip()
    if not target_sentence:
        raise VoiceDiagnosticError('target_sentence must be a non-empty string.')

    comparison = compare_pronunciation(target_sentence, transcript)
    score = comparison['score']
    return {
        'target_sentence': target_sentence,
        'transcript': transcript,
        'score': score,
        'status': _status_for_score(score),
        'feedback': comparison['feedback'],
        'explanation': comparison['explanation'],
        'word_accuracy': comparison['word_accuracy'],
        'missing_words': comparison['missing_words'],
        'extra_words': comparison['extra_words'],
        'substituted_words': comparison['substituted_words'],
        'breakdown': comparison['breakdown'],
    }


def _build_listening_result(question, expected_answer, user_answer):
    question = (question or '').strip()
    expected_answer = (expected_answer or '').strip()
    user_answer = (user_answer or '').strip()
    if not question:
        raise VoiceDiagnosticError('question must be a non-empty string.')
    if not expected_answer:
        raise VoiceDiagnosticError('expected_answer must be a non-empty string.')
    evaluation = _evaluate_listening_rule_based(question, expected_answer, user_answer)
    return {
        'score': evaluation['score'],
        'status': _status_for_score(evaluation['score']),
        'feedback': evaluation['feedback'],
        'explanation': evaluation['explanation'],
        'question': question,
        'expected_answer': expected_answer,
        'user_answer': user_answer,
        'answer': user_answer,
        'matched_keywords': evaluation['matched_keywords'],
        'missing_keywords': evaluation['missing_keywords'],
        'answer_match': evaluation['answer_match'],
        'breakdown': evaluation['breakdown'],
    }


def _build_speaking_result(question, transcript):
    question = (question or '').strip()
    transcript = (transcript or '').strip()
    if not question:
        raise VoiceDiagnosticError('question must be a non-empty string.')

    evaluation = _evaluate_speaking_transcript(question, transcript)
    score = evaluation['score']
    return {
        'question': question,
        'transcript': transcript,
        'score': score,
        'status': _status_for_score(score),
        'feedback': evaluation['feedback'],
        'explanation': evaluation['explanation'],
        'strengths': evaluation['strengths'],
        'improvement_areas': evaluation['improvement_areas'],
        'breakdown': evaluation['breakdown'],
    }


@transaction.atomic
def evaluate_pronunciation(user, audio_file, target_sentence, transcript=None, update_mastery=False):
    transcript = _resolve_transcript(audio_file=audio_file, transcript=transcript)
    result = _build_pronunciation_result(target_sentence, transcript)
    if update_mastery:
        _update_skill_mastery(user, 'Pronunciation', result['score'])
    return result


@transaction.atomic
def evaluate_listening(user, question, expected_answer, user_answer, update_mastery=False):
    result = _build_listening_result(question, expected_answer, user_answer)
    if update_mastery:
        _update_skill_mastery(user, 'Listening', result['score'])
    return result


@transaction.atomic
def evaluate_speaking(user, audio_file, question, transcript=None, update_mastery=False):
    transcript = _resolve_transcript(audio_file=audio_file, transcript=transcript)
    result = _build_speaking_result(question, transcript)
    if update_mastery:
        _update_skill_mastery(user, 'Speaking', result['score'])
    return result


def _validate_batch_items(items, label):
    if not isinstance(items, list) or len(items) != 3:
        raise VoiceDiagnosticError(f'{label} items must contain exactly 3 entries.')
    return items


@transaction.atomic
def evaluate_pronunciation_batch(user, items, session_id=None):
    items = _validate_batch_items(items, 'pronunciation')
    item_results = []
    for index, item in enumerate(items, start=1):
        transcript = _resolve_batch_transcript(item)
        result = _build_pronunciation_result(item.get('target_sentence'), transcript)
        result['item_number'] = index
        item_results.append(result)

    final_score, aggregation = _aggregate_batch_scores(item_results)
    status = _update_skill_mastery(user, 'Pronunciation', final_score)
    result = {
        'items': item_results,
        'final_score': final_score,
        'status': status,
        'level_code': _level_for_score(final_score),
        'feedback_summary': _skill_feedback_summary('pronunciation', final_score, aggregation),
        'aggregation': aggregation,
    }
    session = _persist_voice_diagnostic_batch(
        user,
        'pronunciation',
        result,
        session_id=session_id,
    )
    result.update(serialize_voice_diagnostic_session_state(session))
    return result


@transaction.atomic
def evaluate_listening_batch(user, items, session_id=None):
    items = _validate_batch_items(items, 'listening')
    item_results = []
    for index, item in enumerate(items, start=1):
        result = _build_listening_result(
            item.get('question'),
            item.get('expected_answer'),
            item.get('answer') or item.get('user_answer'),
        )
        result['item_number'] = index
        result['passage'] = (item.get('passage') or '').strip()
        item_results.append(result)

    final_score, aggregation = _aggregate_batch_scores(item_results)
    status = _update_skill_mastery(user, 'Listening', final_score)
    result = {
        'items': item_results,
        'final_score': final_score,
        'status': status,
        'level_code': _level_for_score(final_score),
        'feedback_summary': _skill_feedback_summary('listening', final_score, aggregation),
        'aggregation': aggregation,
    }
    session = _persist_voice_diagnostic_batch(
        user,
        'listening',
        result,
        session_id=session_id,
    )
    result.update(serialize_voice_diagnostic_session_state(session))
    return result


@transaction.atomic
def evaluate_speaking_batch(user, items, session_id=None):
    items = _validate_batch_items(items, 'speaking')
    item_results = []
    for index, item in enumerate(items, start=1):
        transcript = _resolve_batch_transcript(item)
        result = _build_speaking_result(item.get('question'), transcript)
        result['item_number'] = index
        item_results.append(result)

    final_score, aggregation = _aggregate_batch_scores(item_results)
    status = _update_skill_mastery(user, 'Speaking', final_score)
    result = {
        'items': item_results,
        'final_score': final_score,
        'status': status,
        'level_code': _level_for_score(final_score),
        'feedback_summary': _skill_feedback_summary('speaking', final_score, aggregation),
        'aggregation': aggregation,
    }
    session = _persist_voice_diagnostic_batch(
        user,
        'speaking',
        result,
        session_id=session_id,
    )
    result.update(serialize_voice_diagnostic_session_state(session))
    return result
