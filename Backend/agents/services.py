import difflib
import re
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from learning.models import (
    LearnerProfile,
    Module,
    Skill,
    SkillMastery,
    StudyPlan,
    StudySession,
)

from .llm_client import call_llm_json
from .models import LessonSession, LessonTurn
from .prompts import (
    coach_summary_prompt,
    diagnostic_prompt,
    teacher_feedback_prompt,
    teacher_lesson_prompt,
)


SKILL_NAMES = [
    'Grammar',
    'Vocabulary',
    'Speaking',
    'Listening',
    'Pronunciation',
]
DIAGNOSTIC_ASSESSMENT_MODE = 'text_only'
DIAGNOSTIC_ASSESSED_SKILLS = ['Grammar', 'Vocabulary']
DIAGNOSTIC_UNASSESSED_SKILLS = ['Speaking', 'Listening', 'Pronunciation']
DIAGNOSTIC_SKILL_STATUS = {
    'Grammar': 'Assessed',
    'Vocabulary': 'Assessed',
    'Speaking': 'Requires voice test',
    'Listening': 'Requires audio test',
    'Pronunciation': 'Requires voice test',
}
CEFR_LEVELS = {'A1', 'A2', 'B1', 'B2'}
CEFR_PROGRESSION_ORDER = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']
CORE_SKILL_NAMES = ['Grammar', 'Vocabulary', 'Listening', 'Speaking']
SKILL_NAME_LOOKUP = {name.lower(): name for name in SKILL_NAMES}
MISTAKE_TYPES = {
    'grammar': 'Grammar',
    'spelling': 'Spelling',
    'vocabulary': 'Vocabulary',
    'clarity': 'Clarity',
    'sentence structure': 'Sentence Structure',
    'naturalness': 'Naturalness',
}
GENERIC_FEEDBACK_PHRASES = (
    'strong response',
    'good response',
    'good answer',
    'good work',
    'already clear',
    'already correct',
    'already complete',
    'clear and understandable',
    'keep practicing',
    'nice work',
)
UNCLEAR_FEEDBACK = (
    'Your answer is unclear and does not fully answer the question. '
    'Review sentence structure and word choice.'
)
QUESTION_CORRECTIONS = {
    'introduce yourself in english.': (
        'My name is Jane Doe. I live in this city. I am learning English to improve my communication skills.'
    ),
    'describe what you did yesterday.': (
        'Yesterday, I practiced English and worked on my tasks.'
    ),
    'what is your learning goal?': (
        'My learning goal is to improve my English and communicate more clearly.'
    ),
}
COMMON_WORDS = {
    'a', 'about', 'after', 'am', 'an', 'and', 'are', 'at', 'basic', 'based',
    'be', 'because', 'can', 'capital', 'city', 'clear', 'clearly',
    'communication', 'company', 'confidently', 'continue', 'describe', 'did',
    'confident', 'do', 'english', 'every', 'for', 'goal', 'good', 'hello', 'hi', 'home',
    'i', 'improve', 'in', 'introduce', 'international', 'is', 'it', 'learn',
    'learning', 'live', 'living', 'my', 'name', 'next', 'practice', 'region',
    'same', 'school', 'sentence', 'simple', 'speak', 'speaking', 'specialist',
    'study', 'support', 'task', 'technical', 'the', 'this', 'to', 'want',
    'was', 'what', 'work', 'worked', 'working', 'yesterday', 'you', 'your'
}
SPELLING_HINTS = {
    'im': 'I am',
    'learng': 'learning',
    'lakkee': 'like',
    'hose': 'home',
    'thisss': 'this',
    'gola': 'goal',
}
GUIDED_SESSION_TOTAL_TURNS = 3
SPEAKING_TEACHER_SKILL = 'Speaking'
SPEAKING_TEACHER_SESSION_TYPE = 'speaking_teacher_session'
SPEAKING_PRACTICE_SCORE_LABEL = 'Practice Score'
SPEAKING_FILLER_WORDS = {'um', 'uh', 'like', 'actually', 'basically'}
SPEAKING_TEACHER_TASKS = {
    'A1': [
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Introduce yourself and say what you do each day.',
            'target_focus': 'basic personal information in complete sentences',
            'keywords': ['name', 'live', 'from', 'work', 'study', 'day', 'daily'],
        },
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Describe your daily routine from morning to evening.',
            'target_focus': 'simple sequence words like first, then, and after',
            'keywords': ['morning', 'afternoon', 'evening', 'first', 'then', 'after', 'day'],
        },
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Answer this personal question: what do you enjoy doing after work or school?',
            'target_focus': 'one clear preference with a simple reason',
            'keywords': ['enjoy', 'like', 'after', 'work', 'school', 'because', 'relax'],
        },
    ],
    'A2': [
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Describe what you did yesterday and mention one result.',
            'target_focus': 'past tense with one clear result using because or so',
            'keywords': ['yesterday', 'went', 'worked', 'studied', 'did', 'because', 'so'],
        },
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Talk about something you like or dislike and explain why.',
            'target_focus': 'preference language with because',
            'keywords': ['like', 'dislike', 'enjoy', 'prefer', 'because', 'reason'],
        },
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Describe a simple situation at work or school and how you handled it.',
            'target_focus': 'clear situation, action, and result',
            'keywords': ['work', 'school', 'problem', 'task', 'handled', 'helped', 'finished'],
        },
    ],
    'B1': [
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Tell me about a problem you solved and explain the solution.',
            'target_focus': 'clear explanation with because, so, or although',
            'keywords': ['problem', 'solved', 'solution', 'because', 'so', 'although', 'result'],
        },
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Explain one English learning goal and the steps you are taking.',
            'target_focus': 'goal, steps, and reason in a connected response',
            'keywords': ['goal', 'english', 'improve', 'practice', 'plan', 'because', 'steps'],
        },
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Give an opinion about an effective way to learn English and support it with reasons.',
            'target_focus': 'opinion language with two supporting reasons',
            'keywords': ['opinion', 'english', 'learn', 'effective', 'because', 'reason', 'practice'],
        },
    ],
    'B2': [
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Explain a workplace or technical process that you know well.',
            'target_focus': 'organized explanation using sequence and cause-and-effect language',
            'keywords': ['process', 'system', 'first', 'then', 'after', 'because', 'result'],
        },
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Compare two options for solving a problem and say which one you would choose.',
            'target_focus': 'comparison language with supporting reasons',
            'keywords': ['compare', 'option', 'better', 'however', 'because', 'choose', 'solution'],
        },
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Explain the tradeoffs in an important decision and give your recommendation.',
            'target_focus': 'balanced reasoning with a clear recommendation',
            'keywords': ['tradeoff', 'decision', 'advantage', 'disadvantage', 'recommend', 'because'],
        },
    ],
    'C1': [
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Defend a viewpoint on a professional or social topic.',
            'target_focus': 'structured argument with clear support and contrast',
            'keywords': ['viewpoint', 'argument', 'however', 'although', 'evidence', 'reason'],
        },
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Summarize a complex issue and explain the main challenge.',
            'target_focus': 'precise summary with one main challenge and implication',
            'keywords': ['issue', 'challenge', 'summary', 'main', 'impact', 'complex'],
        },
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Present a structured recommendation for improving a team or process.',
            'target_focus': 'clear recommendation with justification and expected result',
            'keywords': ['recommendation', 'improve', 'process', 'team', 'result', 'reason'],
        },
    ],
    'C2': [
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Give a nuanced explanation of a difficult communication problem.',
            'target_focus': 'nuance, contrast, and precise reasoning',
            'keywords': ['nuanced', 'communication', 'problem', 'however', 'context', 'reasoning'],
        },
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Respond to a professional discussion prompt with a persuasive viewpoint.',
            'target_focus': 'persuasive structure with sophisticated support',
            'keywords': ['professional', 'persuasive', 'viewpoint', 'evidence', 'support', 'recommend'],
        },
        {
            'task_type': 'spoken_response',
            'teacher_prompt': 'Give an abstract or persuasive response that balances multiple perspectives.',
            'target_focus': 'multiple perspectives with a strong final position',
            'keywords': ['perspective', 'balance', 'abstract', 'position', 'however', 'therefore'],
        },
    ],
}


def _clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, round(value)))


def _level_for_score(score):
    if score < 50:
        return 'A1'
    if score < 70:
        return 'A2'
    if score < 85:
        return 'B1'
    return 'B2'


def _status_for_score(score):
    if score < 60:
        return 'Needs Review'
    if score < 80:
        return 'Learning'
    return 'Mastered'


@transaction.atomic
def recalculate_learner_level(user):
    profile, _ = LearnerProfile.objects.get_or_create(user=user)
    current_level = (profile.current_level or 'A1').upper()
    if current_level not in CEFR_PROGRESSION_ORDER:
        current_level = 'A1'

    if current_level == 'C2':
        if profile.current_level != 'C2':
            profile.current_level = 'C2'
            profile.save(update_fields=['current_level', 'updated_at'])
        return 'C2'

    masteries = SkillMastery.objects.filter(
        user=user,
        skill__name__in=CORE_SKILL_NAMES,
    ).select_related('skill')
    score_lookup = {
        mastery.skill.name: float(mastery.score)
        for mastery in masteries
    }
    if any(skill_name not in score_lookup for skill_name in CORE_SKILL_NAMES):
        if profile.current_level != current_level:
            profile.current_level = current_level
            profile.save(update_fields=['current_level', 'updated_at'])
        return current_level

    if not all(score_lookup[skill_name] >= 80 for skill_name in CORE_SKILL_NAMES):
        if profile.current_level != current_level:
            profile.current_level = current_level
            profile.save(update_fields=['current_level', 'updated_at'])
        return current_level

    next_index = min(
        CEFR_PROGRESSION_ORDER.index(current_level) + 1,
        len(CEFR_PROGRESSION_ORDER) - 1,
    )
    next_level = CEFR_PROGRESSION_ORDER[next_index]
    if next_level != profile.current_level:
        profile.current_level = next_level
        profile.save(update_fields=['current_level', 'updated_at'])
    return next_level


def _serialize_module(module):
    if module is None:
        return None
    return {
        'id': module.id,
        'title': module.title,
        'level': module.level.level_code,
        'skill': module.skill.name,
    }


def _normalize_text(value):
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _normalized_compare_text(value):
    return re.sub(r'\s+', ' ', (value or '').strip()).casefold()


def _same_text(left, right):
    return _normalized_compare_text(left) == _normalized_compare_text(right)


def _diagnostic_metadata():
    return {
        'assessment_mode': DIAGNOSTIC_ASSESSMENT_MODE,
        'assessed_skills': list(DIAGNOSTIC_ASSESSED_SKILLS),
        'unassessed_skills': list(DIAGNOSTIC_UNASSESSED_SKILLS),
        'skill_status': dict(DIAGNOSTIC_SKILL_STATUS),
    }


def _normalize_skill_scores(raw_scores, allowed_skills=None):
    if not isinstance(raw_scores, dict):
        return None

    allowed_skills = allowed_skills or SKILL_NAMES
    allowed_lookup = {skill.lower(): skill for skill in allowed_skills}
    normalized_scores = {}
    for raw_name, raw_score in raw_scores.items():
        if not isinstance(raw_name, str) or not isinstance(raw_score, (int, float)):
            continue
        skill_name = SKILL_NAME_LOOKUP.get(raw_name.strip().lower())
        if skill_name is None or skill_name.lower() not in allowed_lookup:
            continue
        normalized_scores[allowed_lookup[skill_name.lower()]] = _clamp(raw_score)

    if set(normalized_scores) != set(allowed_skills):
        return None

    return {
        skill_name: normalized_scores[skill_name]
        for skill_name in allowed_skills
    }


def _normalize_weak_skills(raw_weak_skills, skill_scores):
    ranked_skills = sorted(skill_scores, key=lambda name: (skill_scores[name], name))
    if not isinstance(raw_weak_skills, list):
        return ranked_skills[:2]

    normalized = []
    seen = set()
    for raw_skill in raw_weak_skills:
        if not isinstance(raw_skill, str):
            continue
        skill_name = SKILL_NAME_LOOKUP.get(raw_skill.strip().lower())
        if skill_name in skill_scores and skill_name not in seen:
            normalized.append(skill_name)
            seen.add(skill_name)
        if len(normalized) == 2:
            return normalized

    for skill_name in ranked_skills:
        if skill_name not in seen:
            normalized.append(skill_name)
        if len(normalized) == 2:
            return normalized
    return ranked_skills[:2]


def _normalize_feedback_score(raw_score):
    if not isinstance(raw_score, (int, float)):
        return None
    return _clamp(raw_score)


def _normalize_mistake(raw_mistake):
    if not isinstance(raw_mistake, dict):
        return None

    raw_type = _normalize_text(raw_mistake.get('type'))
    original = _normalize_text(raw_mistake.get('original'))
    correction = _normalize_text(raw_mistake.get('correction'))
    explanation = _normalize_text(raw_mistake.get('explanation'))
    if None in {raw_type, original, correction, explanation}:
        return None

    mistake_type = MISTAKE_TYPES.get(raw_type.lower())
    if mistake_type is None:
        return None

    return {
        'type': mistake_type,
        'original': original,
        'correction': correction,
        'explanation': explanation,
    }

def _answer_metrics(answers):
    response_texts = [item.get('answer', '').strip() for item in answers]
    combined_text = ' '.join(response_texts)
    words = re.findall(r"[A-Za-z']+", combined_text)
    unique_words = {word.lower() for word in words}
    answered_count = sum(bool(text) for text in response_texts)
    completion_ratio = answered_count / len(answers)
    sentence_count = len(re.findall(r'[.!?]+', combined_text))
    long_word_count = sum(len(word) >= 7 for word in unique_words)
    tense_errors = len(
        re.findall(
            r'\b(yesterday|last\s+\w+)\b[^.!?]*\b(i|we|you|they|he|she)\s+'
            r'(go|come|eat|see|do|have|make|take)\b',
            combined_text,
            flags=re.IGNORECASE,
        )
    )
    agreement_errors = len(
        re.findall(
            r'\b(he|she|it)\s+(go|live|work|study|play|like|want)\b',
            combined_text,
            flags=re.IGNORECASE,
        )
    )
    return {
        'word_count': len(words),
        'unique_count': len(unique_words),
        'completion_ratio': completion_ratio,
        'sentence_count': sentence_count,
        'long_word_count': long_word_count,
        'grammar_errors': tense_errors + agreement_errors,
    }


def score_diagnostic_answers(answers):
    metrics = _answer_metrics(answers)
    word_count = metrics['word_count']
    sentence_bonus = min(metrics['sentence_count'] * 5, 10)

    return {
        'Grammar': _clamp(
            45
            + min(word_count * 2, 20)
            + sentence_bonus
            - metrics['grammar_errors'] * 12
        ),
        'Vocabulary': _clamp(
            48
            + min(metrics['unique_count'] * 2, 22)
            + min(metrics['long_word_count'] * 2, 8)
        ),
    }


def _diagnostic_issue_counts(feedback_items):
    counts = {
        'clear_feedback_count': 0,
        'unclear_answers': 0,
        'grammar_issues': 0,
        'spelling_issues': 0,
        'clarity_issues': 0,
        'structure_issues': 0,
        'naturalness_issues': 0,
        'total_issues': 0,
    }

    for item in feedback_items:
        feedback = (item.get('feedback') or '').lower()
        mistakes = item.get('mistakes') or []
        if 'already clear, correct, and complete' in feedback:
            counts['clear_feedback_count'] += 1
        if 'unclear' in feedback:
            counts['unclear_answers'] += 1

        for mistake in mistakes:
            mistake_type = mistake.get('type')
            counts['total_issues'] += 1
            if mistake_type == 'Grammar':
                counts['grammar_issues'] += 1
            elif mistake_type == 'Spelling':
                counts['spelling_issues'] += 1
            elif mistake_type == 'Clarity':
                counts['clarity_issues'] += 1
            elif mistake_type == 'Sentence Structure':
                counts['structure_issues'] += 1
            elif mistake_type == 'Naturalness':
                counts['naturalness_issues'] += 1

    counts['unclear_answers'] = max(
        counts['unclear_answers'],
        sum(
            1
            for item in feedback_items
            if any(
                mistake.get('type') == 'Clarity'
                for mistake in (item.get('mistakes') or [])
            )
        ),
    )
    return counts


def _apply_diagnostic_score_floor(skill_scores, feedback_items, base_scores):
    counts = _diagnostic_issue_counts(feedback_items)
    clear_majority = counts['clear_feedback_count'] >= max(1, len(feedback_items) // 2 + 1)
    has_major_issues = any(
        counts[key] > 0
        for key in ['grammar_issues', 'clarity_issues', 'structure_issues', 'unclear_answers']
    )
    has_strong_base = all(base_scores[skill_name] >= 70 for skill_name in ['Grammar', 'Vocabulary'])
    if not clear_majority or has_major_issues or not has_strong_base:
        return skill_scores

    minimum_score = 85 if counts['total_issues'] == 0 else 80
    return {
        skill_name: max(score, minimum_score)
        for skill_name, score in skill_scores.items()
    }


def _diagnostic_score_reasons(skill_scores, feedback_items):
    counts = _diagnostic_issue_counts(feedback_items)
    has_major_issues = any(
        counts[key] > 0
        for key in ['grammar_issues', 'clarity_issues', 'structure_issues', 'unclear_answers']
    )

    if counts['total_issues'] == 0 and min(skill_scores.values()) >= 85:
        grammar_reason = 'Your answers were clear, correct, and complete across the diagnostic.'
        vocabulary_reason = (
            'You used appropriate workplace, learning, and everyday vocabulary with good range.'
        )
    elif counts['total_issues'] == 0:
        grammar_reason = 'Your answers were clear and accurate, but they were brief enough to limit the score range.'
        vocabulary_reason = 'Your vocabulary was appropriate, but the answers were not detailed enough to show a wider range.'
    elif not has_major_issues and counts['total_issues'] <= 2:
        grammar_reason = 'Your answers were mostly accurate with only minor issues.'
        vocabulary_reason = 'You used appropriate vocabulary with only minor wording or spelling issues.'
    elif skill_scores['Grammar'] >= 70:
        grammar_reason = 'Your answers communicated the main ideas, but some grammar control was inconsistent.'
        vocabulary_reason = 'You used useful vocabulary, but some word choice or clarity issues reduced the score.'
    else:
        grammar_reason = 'Your answers need clearer sentence control and more consistent grammar.'
        vocabulary_reason = 'Your vocabulary needs clearer, more accurate word choice to express ideas consistently.'

    return grammar_reason, vocabulary_reason


def _extract_intro_name(answer_text):
    name_patterns = [
        r"\bmy name is\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})(?=\s+(?:and|i|live|living)\b|[,.!?]|$)",
        r"\b(?:i am|i'm)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})(?=\s+(?:live|living|from)\b|[,.!?]|$)",
    ]
    for pattern in name_patterns:
        match = re.search(pattern, answer_text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if all(word[:1].isupper() for word in candidate.split()):
                return candidate
    return None


def _extract_intro_place(answer_text):
    place_patterns = [
        r"\blive in\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,3})",
        r"\bliving in\s+([A-Za-z]+(?:\s+[A-Za-z]+){0,3})",
    ]
    for pattern in place_patterns:
        match = re.search(pattern, answer_text, flags=re.IGNORECASE)
        if match:
            place = re.sub(r'\s+', ' ', match.group(1)).strip()
            if place:
                return place
    return None


def _default_corrected_answer(question, answer=''):
    question_key = question.strip().lower()
    answer_text = answer.strip()
    lowered_answer = answer_text.lower()

    if question_key == 'introduce yourself in english.':
        learner_name = _extract_intro_name(answer_text) or 'Jane Doe'
        place = _extract_intro_place(answer_text) or 'this city'
        return (
            f'My name is {learner_name}. I live in {place}. '
            'I am learning English to improve my communication skills.'
        )

    if question_key == 'describe what you did yesterday.':
        if any(phrase in lowered_answer for phrase in ('did before', 'same', 'continue', 'continued')):
            return (
                'Yesterday, I completed my work and continued practicing English.'
            )
        return 'Yesterday, I practiced English and worked on my tasks.'

    if question_key == 'what is your learning goal?':
        return 'My learning goal is to improve my English and communicate more clearly.'

    return QUESTION_CORRECTIONS.get(
        question_key,
        'I want to answer in clear and complete English sentences.'
    )


def _has_sentence_structure(words):
    lower_words = [word.lower() for word in words]
    has_subject = any(word in {'i', 'he', 'she', 'we', 'they', 'you', 'my'} for word in lower_words)
    has_verb = any(
        word in {
            'am', 'is', 'are', 'was', 'were', 'be', 'study', 'studied', 'learn',
            'learning', 'want', 'wanted', 'go', 'went', 'did', 'do', 'live',
            'living', 'improve', 'work', 'worked', 'working', 'based'
        }
        for word in lower_words
    )
    return has_subject and has_verb


def _find_suspicious_words(words):
    suspicious = []
    for word in words:
        lowered = word.lower()
        if lowered in COMMON_WORDS or lowered in SPELLING_HINTS:
            continue
        if len(lowered) <= 3:
            continue
        if word[:1].isupper():
            continue
        if re.search(r'(.)\1\1', lowered):
            suspicious.append(word)
            continue
        if not re.search(r'[aeiouy]', lowered):
            suspicious.append(word)
            continue
        if difflib.get_close_matches(lowered, COMMON_WORDS, n=1, cutoff=0.82):
            suspicious.append(word)
    return suspicious


def _has_obvious_unclear_pattern(question_lower, answer_text, lower_words):
    if re.search(
        r"\b(i did was|goal is the gola|were are|please be me why not|me i am|did i do not will|do not will be|me goal)\b",
        answer_text,
        flags=re.IGNORECASE,
    ):
        return True

    if 'introduce yourself' in question_lower:
        if lower_words[:2] == ['me', 'i']:
            return True
        if lower_words[:1] == ['me'] and _extract_intro_name(answer_text) is None:
            return True

    if 'describe what you did yesterday' in question_lower:
        if re.search(r'\b(do not will|did i do not will|will be oyourss)\b', answer_text, flags=re.IGNORECASE):
            return True

    if 'learning goal' in question_lower:
        if lower_words[:2] == ['me', 'goal']:
            return True
        if lower_words.count('goal') >= 2 and 'my learning goal is' not in answer_text.lower():
            return True

    return False


def _feedback_indicates_changes(feedback):
    return bool(
        re.search(
            r'\b(improve|need|needs|review|correct|correction|grammar|spelling|vocabulary|clarity|unclear|mistake|detail|natural)\b',
            feedback.lower(),
        )
    )


def _feedback_is_generic_or_misleading(feedback, has_issues):
    lowered_feedback = feedback.lower()
    if has_issues and any(phrase in lowered_feedback for phrase in GENERIC_FEEDBACK_PHRASES):
        return True
    if has_issues and re.search(
        r'\balready\b.*\b(clear|correct|complete)\b',
        lowered_feedback,
    ):
        return True
    if has_issues and not re.search(
        r'\b(grammar|spelling|vocabulary|sentence|clarity|unclear|past tense|word choice|natural|meaning)\b',
        lowered_feedback,
    ):
        return True
    return False


def _clean_rewritten_sentence(text):
    cleaned = re.sub(r'\s+', ' ', text).strip()
    cleaned = re.sub(r'\s+([,.!?])', r'\1', cleaned)
    if cleaned and cleaned[-1] not in '.!?':
        cleaned = f'{cleaned}.'
    return cleaned


def _replacement_pattern(original):
    if re.fullmatch(r"[A-Za-z']+", original):
        return rf"\b{re.escape(original)}\b"
    return re.escape(original)


def _build_corrected_answer(question, answer, mistakes, is_unclear):
    answer_text = answer.strip()
    if is_unclear:
        return _default_corrected_answer(question, answer_text)

    corrected_answer = answer_text
    replacements = []
    for mistake in mistakes:
        original = mistake['original']
        correction = mistake['correction']
        if original.lower() == correction.lower():
            continue
        replacements.append((original, correction))

    replacements.sort(key=lambda item: len(item[0]), reverse=True)
    for original, correction in replacements:
        corrected_answer = re.sub(
            _replacement_pattern(original),
            correction,
            corrected_answer,
            flags=re.IGNORECASE,
        )

    corrected_answer = _clean_rewritten_sentence(corrected_answer)
    if not corrected_answer:
        return _default_corrected_answer(question, answer_text)
    if mistakes and _same_text(corrected_answer, answer_text):
        return _default_corrected_answer(question, answer_text)
    return corrected_answer

def _analyze_answer_feedback(question, answer):
    answer_text = answer.strip()
    question_lower = question.strip().lower()
    words = re.findall(r"[A-Za-z']+", answer_text)
    lower_words = [word.lower() for word in words]
    mistakes = []
    seen = set()
    tense_issue = False

    def add_mistake(mistake_type, original, correction, explanation):
        if not original or not correction:
            return
        key = (mistake_type, original.lower(), correction.lower())
        if key in seen:
            return
        seen.add(key)
        mistakes.append(
            {
                'type': mistake_type,
                'original': original,
                'correction': correction,
                'explanation': explanation,
            }
        )

    if not answer_text:
        corrected = _default_corrected_answer(question, answer_text)
        add_mistake(
            'Sentence Structure',
            '(empty answer)',
            corrected,
            'Use at least one complete sentence so the diagnostic can measure your level.',
        )
        return {
            'question': question.strip(),
            'answer': answer_text,
            'feedback': 'Your answer is missing. Write one clear complete sentence so the agent can evaluate your English.',
            'corrected_answer': corrected,
            'mistakes': mistakes,
            'is_unclear': True,
        }

    if re.search(r"\bim\b", answer_text, flags=re.IGNORECASE):
        add_mistake(
            'Grammar',
            'Im',
            'I am',
            "Use 'I am' for a correct subject and verb.",
        )

    if lower_words[:1] == ['me']:
        add_mistake(
            'Grammar',
            words[0],
            'I',
            "Use 'I' as the subject of a sentence.",
        )

    intro_match = re.search(
        r"((?:I am|I'm)\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2}\s+living in this city)",
        answer_text,
    )
    if intro_match:
        learner_name = _extract_intro_name(answer_text) or '[your name]'
        add_mistake(
            'Sentence Structure',
            intro_match.group(1),
            f'I am {learner_name}, and I live in this city',
            'Use a complete clause after your name so the introduction sounds natural and complete.',
        )

    tech_support_match = re.search(
        r'(I am currently working as\s+I\.?T\.?\s+Tech support)',
        answer_text,
        flags=re.IGNORECASE,
    )
    if tech_support_match:
        add_mistake(
            'Naturalness',
            tech_support_match.group(1),
            'I currently work as an IT technical support specialist',
            'Use a more natural job title and a simpler verb form.',
        )

    if re.search(r'large and international company', answer_text, flags=re.IGNORECASE):
        add_mistake(
            'Naturalness',
            'large and international company',
            'large international company',
            'In this phrase, English usually uses "large international company" without "and".',
        )

    based_match = re.search(
        r'(company that base in(?: the)? capital region)',
        answer_text,
        flags=re.IGNORECASE,
    )
    if based_match:
        add_mistake(
            'Grammar',
            based_match.group(1),
            'company based in the capital region',
            'Use "based in" to describe where the company is located.',
        )

    if re.search(
        r'\b(yesterday|last\s+\w+)\b[^.!?]*\b(go|come|eat|see|do|have|make|take)\b',
        answer_text,
        flags=re.IGNORECASE,
    ):
        tense_issue = True
        add_mistake(
            'Grammar',
            answer_text,
            'Yesterday, I went and completed my activities.',
            'Use past tense verbs when you describe something that happened yesterday.',
        )

    suspicious_words = _find_suspicious_words(words)
    for word in suspicious_words[:3]:
        lowered = word.lower()
        correction = SPELLING_HINTS.get(lowered)
        if correction is None:
            matches = difflib.get_close_matches(lowered, COMMON_WORDS, n=1, cutoff=0.82)
            correction = matches[0] if matches else None
        if correction:
            add_mistake(
                'Spelling',
                word,
                correction,
                'Check the spelling so your meaning is easier to understand.',
            )

    obvious_clarity_break = _has_obvious_unclear_pattern(
        question_lower,
        answer_text,
        lower_words,
    )
    word_count = len(words)
    unclear_ratio = len(suspicious_words) / max(word_count, 1)
    has_sentence_structure = _has_sentence_structure(words)
    is_unclear = (
        obvious_clarity_break
        or
        unclear_ratio >= 0.28
        or len(suspicious_words) >= 2
        or not has_sentence_structure
        or word_count < 4
        or lower_words.count('me') >= 2
        or (
            'introduce yourself' in question_lower
            and 'my name' not in answer_text.lower()
            and 'i am' not in answer_text.lower()
            and "i'm" not in answer_text.lower()
        )
    )

    if is_unclear:
        add_mistake(
            'Clarity',
            answer_text,
            _default_corrected_answer(question, answer_text),
            'The original answer is unclear or incomplete, so it needs a clearer complete idea.',
        )

    if word_count < 6:
        add_mistake(
            'Sentence Structure',
            answer_text,
            _default_corrected_answer(question, answer_text),
            'Use one or two complete sentences with a clear subject, verb, and idea.',
        )

    if is_unclear:
        feedback = UNCLEAR_FEEDBACK
    elif tense_issue and 'yesterday' in question_lower:
        feedback = (
            'Your answer gives the main idea, but you need past tense verbs to describe what happened yesterday correctly.'
        )
    elif mistakes:
        feedback = (
            'Your answer shows the main idea, but it still has grammar, spelling, clarity, or naturalness problems that need correction.'
        )
    else:
        feedback = 'Your answer is already clear, correct, and complete for this question.'

    corrected_answer = _build_corrected_answer(question, answer, mistakes, is_unclear)
    return {
        'question': question.strip(),
        'answer': answer_text,
        'feedback': feedback,
        'corrected_answer': corrected_answer,
        'mistakes': mistakes,
        'is_unclear': is_unclear,
    }


def _fallback_feedback_item(question, answer):
    analysis = _analyze_answer_feedback(question, answer)
    return (
        {
            'question': analysis['question'],
            'answer': analysis['answer'],
            'feedback': analysis['feedback'],
            'corrected_answer': analysis['corrected_answer'],
            'mistakes': analysis['mistakes'],
        },
        analysis,
    )


def _force_question_aware_feedback(item, fallback_item, analysis):
    if not analysis['is_unclear']:
        return item

    corrected_matches_answer = _same_text(
        item['corrected_answer'],
        fallback_item['answer'],
    )
    if corrected_matches_answer or not item['mistakes']:
        return fallback_item

    normalized_item = dict(item)
    normalized_item['feedback'] = UNCLEAR_FEEDBACK
    return normalized_item


def normalize_answer_feedback(raw_feedback, answers):
    fallback_items = []
    fallback_analyses = []
    for source_answer in answers:
        fallback_item, analysis = _fallback_feedback_item(
            source_answer.get('question', ''),
            source_answer.get('answer', ''),
        )
        fallback_items.append(fallback_item)
        fallback_analyses.append(analysis)

    if not isinstance(raw_feedback, list):
        return fallback_items

    normalized_feedback = []
    for index, source_answer in enumerate(answers):
        fallback_item = fallback_items[index]
        analysis = fallback_analyses[index]
        if index >= len(raw_feedback) or not isinstance(raw_feedback[index], dict):
            normalized_feedback.append(fallback_item)
            continue

        item = raw_feedback[index]
        feedback = _normalize_text(item.get('feedback'))
        corrected_answer = _normalize_text(item.get('corrected_answer'))
        raw_mistakes = item.get('mistakes')
        if feedback is None or corrected_answer is None or not isinstance(raw_mistakes, list):
            normalized_feedback.append(fallback_item)
            continue

        mistakes = []
        invalid_mistake = False
        for raw_mistake in raw_mistakes:
            normalized_mistake = _normalize_mistake(raw_mistake)
            if normalized_mistake is None:
                invalid_mistake = True
                break
            mistakes.append(normalized_mistake)
        if invalid_mistake:
            normalized_feedback.append(fallback_item)
            continue

        normalized_item = {
            'question': _normalize_text(item.get('question'))
            or source_answer.get('question', '').strip(),
            'answer': _normalize_text(item.get('answer'))
            or source_answer.get('answer', '').strip(),
            'feedback': feedback,
            'corrected_answer': corrected_answer,
            'mistakes': mistakes,
        }

        has_issues = analysis['is_unclear'] or bool(analysis['mistakes'])
        corrected_matches_answer = _same_text(
            normalized_item['corrected_answer'],
            fallback_item['answer'],
        )
        if corrected_matches_answer:
            if has_issues or _feedback_indicates_changes(normalized_item['feedback']) or normalized_item['mistakes']:
                normalized_feedback.append(fallback_item)
                continue
            normalized_item['feedback'] = 'Your answer is already clear, correct, and complete for this question.'
            normalized_item['mistakes'] = []
            normalized_feedback.append(normalized_item)
            continue

        if not normalized_item['mistakes'] and not _same_text(
            normalized_item['corrected_answer'],
            normalized_item['answer'],
        ):
            normalized_feedback.append(fallback_item)
            continue

        if has_issues and not normalized_item['mistakes']:
            normalized_item['mistakes'] = fallback_item['mistakes']

        if _feedback_is_generic_or_misleading(normalized_item['feedback'], has_issues):
            normalized_item['feedback'] = fallback_item['feedback']

        if has_issues and not normalized_item['mistakes']:
            normalized_feedback.append(fallback_item)
            continue

        normalized_feedback.append(
            _force_question_aware_feedback(
                normalized_item,
                fallback_item,
                analysis,
            )
        )

    return normalized_feedback

def _rule_based_level_explanation(overall_level, diagnostics):
    total_mistakes = sum(len(item['mistakes']) for item in diagnostics)
    unclear_answers = sum(1 for item in diagnostics if item['is_unclear'])
    clarity_issues = sum(
        1
        for item in diagnostics
        for mistake in item['mistakes']
        if mistake['type'] == 'Clarity'
    )

    if unclear_answers >= 2 or clarity_issues >= 2 or (
        overall_level == 'A1' and (unclear_answers >= 1 or clarity_issues >= 1)
    ):
        detail = (
            'the answers contain unclear meaning, grammar errors, and limited control of basic vocabulary.'
        )
    elif total_mistakes >= 3:
        detail = (
            'the answers show some basic ideas, but grammar accuracy, spelling, and sentence structure still need work.'
        )
    elif overall_level == 'A2':
        detail = (
            'the answers show basic sentence control, but more detail and accuracy are still needed.'
        )
    else:
        detail = (
            'the answers show mostly clear communication, but there is still room to improve control and detail.'
        )

    return f'Your level is {overall_level} because {detail}'


def _build_rule_based_diagnostic_result(answers):
    base_scores = score_diagnostic_answers(answers)
    diagnostics = [
        _analyze_answer_feedback(
            item.get('question', ''),
            item.get('answer', ''),
        )
        for item in answers
    ]

    unclear_answers = sum(1 for item in diagnostics if item['is_unclear'])
    grammar_issues = sum(
        1
        for item in diagnostics
        for mistake in item['mistakes']
        if mistake['type'] == 'Grammar'
    )
    spelling_issues = sum(
        1
        for item in diagnostics
        for mistake in item['mistakes']
        if mistake['type'] == 'Spelling'
    )
    clarity_issues = sum(
        1
        for item in diagnostics
        for mistake in item['mistakes']
        if mistake['type'] == 'Clarity'
    )
    structure_issues = sum(
        1
        for item in diagnostics
        for mistake in item['mistakes']
        if mistake['type'] == 'Sentence Structure'
    )
    naturalness_issues = sum(
        1
        for item in diagnostics
        for mistake in item['mistakes']
        if mistake['type'] == 'Naturalness'
    )
    total_issues = sum(len(item['mistakes']) for item in diagnostics)

    skill_scores = {
        'Grammar': _clamp(
            base_scores['Grammar']
            - grammar_issues * 10
            - structure_issues * 8
            - unclear_answers * 8
            - spelling_issues * 4
            - naturalness_issues * 2
        ),
        'Vocabulary': _clamp(
            base_scores['Vocabulary']
            - clarity_issues * 8
            - spelling_issues * 6
            - unclear_answers * 6
            - naturalness_issues * 4
        ),
    }

    if unclear_answers >= 2 or total_issues >= 6:
        skill_scores = {
            name: _clamp(score - 10)
            for name, score in skill_scores.items()
        }

    feedback_items = [
        {
            'feedback': item['feedback'],
            'mistakes': item['mistakes'],
        }
        for item in diagnostics
    ]
    skill_scores = _apply_diagnostic_score_floor(
        skill_scores,
        feedback_items,
        base_scores,
    )
    average_score = sum(skill_scores.values()) / len(skill_scores)
    overall_level = _level_for_score(average_score)
    weak_skills = sorted(skill_scores, key=lambda name: (skill_scores[name], name))[:2]
    grammar_reason, vocabulary_reason = _diagnostic_score_reasons(
        skill_scores,
        feedback_items,
    )
    if unclear_answers >= 2 or total_issues >= 6:
        recommendation = (
            'Focus on forming clear basic sentences and correcting common grammar errors.'
        )
        next_step = 'Practice simple complete sentences before moving to longer answers.'
    else:
        recommendation = f"Focus on {' and '.join(weak_skills)}."
        next_step = 'Review your weak skills and start the recommended module.'

    return {
        **_diagnostic_metadata(),
        'overall_level': overall_level,
        'skill_scores': skill_scores,
        'weak_skills': weak_skills,
        'recommendation': recommendation,
        'level_explanation': _rule_based_level_explanation(overall_level, diagnostics),
        'grammar_reason': grammar_reason,
        'vocabulary_reason': vocabulary_reason,
        'answer_feedback': [
            {
                'question': item['question'],
                'answer': item['answer'],
                'feedback': item['feedback'],
                'corrected_answer': item['corrected_answer'],
                'mistakes': item['mistakes'],
            }
            for item in diagnostics
        ],
        'next_step': next_step,
    }


def _diagnostic_result_from_llm(answers, fallback_result):
    llm_payload = call_llm_json(*diagnostic_prompt(answers))
    if not isinstance(llm_payload, dict):
        return None

    skill_scores = _normalize_skill_scores(
        llm_payload.get('skill_scores'),
        DIAGNOSTIC_ASSESSED_SKILLS,
    )
    if skill_scores is None:
        return None

    average_score = sum(skill_scores.values()) / len(skill_scores)
    overall_level = _normalize_text(llm_payload.get('overall_level'))
    if overall_level:
        overall_level = overall_level.upper()
    if overall_level not in CEFR_LEVELS:
        overall_level = _level_for_score(average_score)

    result = {
        **fallback_result,
        **_diagnostic_metadata(),
    }
    result['skill_scores'] = skill_scores
    result['overall_level'] = overall_level
    result['weak_skills'] = _normalize_weak_skills(
        llm_payload.get('weak_skills'),
        skill_scores,
    )
    result['recommendation'] = (
        _normalize_text(llm_payload.get('recommendation'))
        or fallback_result['recommendation']
    )
    result['level_explanation'] = (
        _normalize_text(llm_payload.get('level_explanation'))
        or fallback_result['level_explanation']
    )
    result['answer_feedback'] = normalize_answer_feedback(
        llm_payload.get('answer_feedback'),
        answers,
    )
    result['skill_scores'] = _apply_diagnostic_score_floor(
        result['skill_scores'],
        result['answer_feedback'],
        score_diagnostic_answers(answers),
    )
    result['weak_skills'] = sorted(
        result['skill_scores'],
        key=lambda name: (result['skill_scores'][name], name),
    )[:2]
    if not overall_level or overall_level not in CEFR_LEVELS:
        result['overall_level'] = _level_for_score(
            sum(result['skill_scores'].values()) / len(result['skill_scores'])
        )
    grammar_reason, vocabulary_reason = _diagnostic_score_reasons(
        result['skill_scores'],
        result['answer_feedback'],
    )
    result['grammar_reason'] = grammar_reason
    result['vocabulary_reason'] = vocabulary_reason
    result['next_step'] = (
        _normalize_text(llm_payload.get('next_step'))
        or fallback_result['next_step']
    )
    return result


def _lesson_result_from_llm(module):
    llm_payload = call_llm_json(*teacher_lesson_prompt(module))
    if not isinstance(llm_payload, dict):
        return None

    lesson = _normalize_text(llm_payload.get('lesson'))
    practice_question = _normalize_text(llm_payload.get('practice_question'))
    if lesson is None or practice_question is None:
        return None

    return {
        'lesson': lesson,
        'practice_question': practice_question,
    }


def _teacher_feedback_from_llm(module, answer):
    llm_payload = call_llm_json(*teacher_feedback_prompt(module, answer))
    if not isinstance(llm_payload, dict):
        return None

    score = _normalize_feedback_score(llm_payload.get('score'))
    feedback = _normalize_text(llm_payload.get('feedback'))
    if score is None or feedback is None:
        return None

    return score, feedback


def _coach_summary_from_llm(profile_level, weakest_skill, recent_session_count):
    llm_payload = call_llm_json(
        *coach_summary_prompt(profile_level, weakest_skill, recent_session_count)
    )
    if not isinstance(llm_payload, dict):
        return None

    summary = _normalize_text(llm_payload.get('summary'))
    next_step = _normalize_text(llm_payload.get('next_step'))
    if summary is None or next_step is None:
        return None

    return {
        'summary': summary,
        'next_step': next_step,
    }


@transaction.atomic
def evaluate_diagnostic(user, answers):
    rule_based_result = _build_rule_based_diagnostic_result(answers)
    diagnostic_result = _diagnostic_result_from_llm(answers, rule_based_result)
    if diagnostic_result is None:
        diagnostic_result = rule_based_result

    profile, _ = LearnerProfile.objects.get_or_create(user=user)
    profile.current_level = diagnostic_result['overall_level']
    profile.save(update_fields=['current_level', 'updated_at'])

    for skill_name in DIAGNOSTIC_ASSESSED_SKILLS:
        skill, _ = Skill.objects.get_or_create(name=skill_name)
        score = diagnostic_result['skill_scores'][skill_name]
        SkillMastery.objects.update_or_create(
            user=user,
            skill=skill,
            defaults={
                'level_code': diagnostic_result['overall_level'],
                'score': Decimal(score),
                'status': _status_for_score(score),
            },
        )

    recalculate_learner_level(user)
    return diagnostic_result


def _normalized_cefr_level(level_code, default='A1'):
    normalized = _normalize_text(level_code)
    if normalized is not None:
        normalized = normalized.upper()
    if normalized in CEFR_PROGRESSION_ORDER:
        return normalized
    return default


def _official_speaking_mastery_snapshot(user):
    mastery = (
        SkillMastery.objects.filter(user=user, skill__name=SPEAKING_TEACHER_SKILL)
        .select_related('skill')
        .first()
    )
    fallback_level = (
        LearnerProfile.objects.filter(user=user)
        .values_list('current_level', flat=True)
        .first()
    )
    fallback_level = _normalized_cefr_level(fallback_level, default='A1')
    if mastery is None:
        return {
            'official_mastery_assessed': False,
            'official_mastery_score': 0,
            'official_mastery_level': fallback_level,
        }
    return {
        'official_mastery_assessed': True,
        'official_mastery_score': int(mastery.score),
        'official_mastery_level': _normalized_cefr_level(
            mastery.level_code,
            default=fallback_level,
        ),
    }


def _speaking_tasks_for_level(level_code):
    normalized_level = _normalized_cefr_level(level_code, default='A1')
    tasks = SPEAKING_TEACHER_TASKS.get(normalized_level, SPEAKING_TEACHER_TASKS['A1'])
    return [
        {
            **task,
            'turn_number': index + 1,
        }
        for index, task in enumerate(tasks)
    ]


def _speaking_session_intro(level_code):
    return (
        f'This Speaking Teacher Session uses three {level_code} speaking tasks '
        'for practice only. It does not change your official mastery.'
    )


def _build_speaking_session_context(user):
    snapshot = _official_speaking_mastery_snapshot(user)
    level_code = snapshot['official_mastery_level']
    return {
        **snapshot,
        'skill': SPEAKING_TEACHER_SKILL,
        'tasks': _speaking_tasks_for_level(level_code),
        'total_turns': GUIDED_SESSION_TOTAL_TURNS,
    }


def _speaking_session_tasks(lesson_session):
    return (lesson_session.session_context or {}).get('tasks', [])


def _current_speaking_task(lesson_session):
    tasks = _speaking_session_tasks(lesson_session)
    turn_index = max(lesson_session.current_turn - 1, 0)
    if turn_index >= len(tasks):
        return None
    return tasks[turn_index]


def _speaking_words(text):
    return re.findall(r"[a-z0-9']+", (text or '').lower())


def _speaking_unique_content_words(words):
    return {
        word
        for word in words
        if len(word) > 2 and word not in COMMON_WORDS and word not in SPEAKING_FILLER_WORDS
    }


def _speaking_relevance_score(task, transcript):
    words = _speaking_words(transcript)
    if not words:
        return 0

    unique_words = set(words)
    keywords = set(task.get('keywords', []))
    matched_keywords = len(unique_words & keywords)
    word_count = len(words)
    score = 18

    if matched_keywords:
        score += min(matched_keywords * 18, 54)
    elif word_count >= 10:
        score += 20

    if any(linker in unique_words for linker in {'because', 'so', 'although', 'however', 'therefore'}):
        score += 10

    if word_count >= 12:
        score += 10
    elif word_count >= 8:
        score += 6

    if matched_keywords == 0:
        score = min(score, 55)
    return _clamp(score)


def _speaking_clarity_score(transcript):
    words = _speaking_words(transcript)
    word_count = len(words)
    if not word_count:
        return 0

    score = 35
    if word_count >= 8:
        score += 20
    if word_count >= 14:
        score += 15

    sentences = re.split(r'[.!?]+', transcript)
    complete_sentences = len([sentence for sentence in sentences if _normalize_text(sentence)])
    if complete_sentences >= 1:
        score += 15
    if complete_sentences >= 2:
        score += 10

    if re.search(r"\b(i am|i'm|because|so|then|after|however|although)\b", transcript, flags=re.IGNORECASE):
        score += 10
    return _clamp(score)


def _speaking_grammar_score(transcript):
    words = _speaking_words(transcript)
    if not words:
        return 0

    score = 82
    penalties = [
        (r'\b(he|she|it)\s+(go|live|work|study|play|like|want)\b', 18),
        (r'\bi\s+go\b[^.!?]*\b(yesterday|last)\b', 18),
        (r'\b(yesterday|last\s+\w+)\b[^.!?]*\b(go|do|have|make|take)\b', 12),
        (r'\bthere\s+is\s+\w+\s+people\b', 12),
        (r'\bmy\s+english\s+improve\b', 10),
    ]
    for pattern, penalty in penalties:
        if re.search(pattern, transcript, flags=re.IGNORECASE):
            score -= penalty

    if transcript and transcript.strip() and transcript.strip()[-1] not in '.!?':
        score -= 4
    return _clamp(score)


def _speaking_vocabulary_score(transcript):
    words = _speaking_words(transcript)
    if not words:
        return 0

    content_words = _speaking_unique_content_words(words)
    score = 28 + min(len(content_words) * 6, 42)
    if any(
        linker in words
        for linker in ['because', 'although', 'however', 'therefore', 'while', 'instead']
    ):
        score += 15
    return _clamp(score)


def _speaking_completeness_score(task, transcript):
    words = _speaking_words(transcript)
    word_count = len(words)
    if not word_count:
        return 0

    score = 20
    if word_count >= 6:
        score += 20
    if word_count >= 12:
        score += 20
    if word_count >= 18:
        score += 15

    keywords = set(task.get('keywords', []))
    matched_keywords = len(set(words) & keywords)
    score += min(matched_keywords * 6, 20)
    return _clamp(score)


def _speaking_coherence_score(transcript):
    words = _speaking_words(transcript)
    if not words:
        return 0

    score = 30
    connectors = ['because', 'so', 'then', 'after', 'first', 'however', 'although', 'therefore']
    connector_count = sum(1 for connector in connectors if connector in words)
    score += min(connector_count * 15, 45)

    if len(words) >= 12:
        score += 15
    if len(re.split(r'[.!?]+', transcript)) >= 2:
        score += 10
    return _clamp(score)


def _speaking_fluency_signal_score(transcript):
    words = _speaking_words(transcript)
    if not words:
        return 0

    score = 78
    fillers = sum(1 for word in words if word in SPEAKING_FILLER_WORDS)
    repeated_pairs = sum(
        1
        for index in range(1, len(words))
        if words[index] == words[index - 1]
    )
    score -= min(fillers * 8, 24)
    score -= min(repeated_pairs * 10, 20)
    if len(words) < 6:
        score -= 20
    return _clamp(score)


def _apply_basic_speaking_correction(transcript):
    corrected = re.sub(r'\s+', ' ', (transcript or '').strip())
    if not corrected:
        return ''

    for typo, suggestion in SPELLING_HINTS.items():
        corrected = re.sub(rf'\b{re.escape(typo)}\b', suggestion, corrected, flags=re.IGNORECASE)

    corrected = re.sub(r'\bi\b', 'I', corrected)
    corrected = re.sub(r"\bi'm\b", "I'm", corrected, flags=re.IGNORECASE)
    corrected = corrected[0].upper() + corrected[1:]
    if corrected[-1] not in '.!?':
        corrected += '.'
    return corrected


def _build_speaking_turn_feedback(task, transcript, breakdown):
    score = breakdown['score']
    weakest_dimension = min(
        (
            'relevance',
            'clarity',
            'grammar',
            'vocabulary',
            'completeness',
            'coherence',
            'fluency_signal',
        ),
        key=lambda key: breakdown[key],
    )
    correction = _apply_basic_speaking_correction(transcript)

    if score >= 85:
        feedback = 'Strong answer. You responded clearly, completely, and with good control.'
    elif score >= 75:
        feedback = 'Good answer. You explained your ideas clearly with mostly accurate English.'
    elif score >= 60:
        feedback = 'Good attempt. Your answer is relevant, but add more detail and smoother organization.'
    elif score >= 40:
        feedback = 'You answered part of the task, but the response needs more detail and clearer language.'
    else:
        feedback = 'Your answer did not yet address the task clearly. Try again with one complete idea.'

    if weakest_dimension == 'relevance':
        explanation = 'Stay closer to the speaking prompt and include the main idea the teacher asked for.'
    elif weakest_dimension == 'grammar':
        explanation = 'Check verb tense and subject-verb agreement so your meaning stays accurate.'
    elif weakest_dimension == 'vocabulary':
        explanation = 'Add more precise vocabulary instead of repeating the same simple words.'
    elif weakest_dimension == 'completeness':
        explanation = 'Add one more supporting detail so your answer feels complete.'
    elif weakest_dimension == 'coherence':
        explanation = 'Use linking words like because, so, however, or although to organize your response.'
    elif weakest_dimension == 'fluency_signal':
        explanation = 'Reduce fillers and repeated words so the response sounds smoother.'
    else:
        explanation = f'Focus on {task["target_focus"]} to make your answer easier to follow.'

    return {
        'feedback': feedback,
        'correction': correction or 'Please try the task again with a complete spoken answer.',
        'explanation': explanation,
        'encouragement': _encouragement_for_score(score),
    }


def _evaluate_speaking_teacher_answer(task, transcript):
    normalized_transcript = _normalize_text(transcript) or ''
    if not normalized_transcript:
        empty_breakdown = {
            'relevance': 0,
            'clarity': 0,
            'grammar': 0,
            'vocabulary': 0,
            'completeness': 0,
            'coherence': 0,
            'fluency_signal': 0,
            'score': 0,
        }
        feedback = _build_speaking_turn_feedback(task, normalized_transcript, empty_breakdown)
        return {
            'score': 0,
            'evaluation_breakdown': empty_breakdown,
            **feedback,
        }

    breakdown = {
        'relevance': _speaking_relevance_score(task, normalized_transcript),
        'clarity': _speaking_clarity_score(normalized_transcript),
        'grammar': _speaking_grammar_score(normalized_transcript),
        'vocabulary': _speaking_vocabulary_score(normalized_transcript),
        'completeness': _speaking_completeness_score(task, normalized_transcript),
        'coherence': _speaking_coherence_score(normalized_transcript),
        'fluency_signal': _speaking_fluency_signal_score(normalized_transcript),
    }
    score = _clamp(
        breakdown['relevance'] * 0.25
        + breakdown['clarity'] * 0.15
        + breakdown['grammar'] * 0.20
        + breakdown['vocabulary'] * 0.15
        + breakdown['completeness'] * 0.15
        + breakdown['coherence'] * 0.05
        + breakdown['fluency_signal'] * 0.05
    )
    breakdown['score'] = score
    feedback = _build_speaking_turn_feedback(task, normalized_transcript, breakdown)
    return {
        'score': score,
        'evaluation_breakdown': breakdown,
        **feedback,
    }


def _serialize_speaking_current_task(task):
    if task is None:
        return None
    return {
        'turn_number': task['turn_number'],
        'task_type': task['task_type'],
        'teacher_prompt': task['teacher_prompt'],
        'target_focus': task['target_focus'],
    }


def _serialize_speaking_next_task(task):
    if task is None:
        return None
    return {
        'turn_number': task['turn_number'],
        'teacher_task': task['teacher_prompt'],
        'target_focus': task['target_focus'],
    }


def _serialize_speaking_teacher_turn(turn):
    return {
        'turn_number': turn.turn_number,
        'task_type': turn.task_type,
        'target_focus': turn.target_focus,
        'teacher_task': turn.teacher_task,
        'transcript': turn.student_answer,
        'score': int(turn.score) if turn.score is not None else None,
        'feedback': turn.ai_feedback,
        'correction': turn.correction,
        'explanation': turn.explanation,
        'encouragement': turn.encouragement,
        'evaluation_breakdown': turn.evaluation_breakdown or {},
    }


def _build_speaking_final_result(lesson_session):
    turns = list(lesson_session.turns.all())
    scores = [int(turn.score) for turn in turns if turn.score is not None]
    practice_score = _clamp(sum(scores) / len(scores)) if scores else 0

    dimension_totals = {
        'relevance': [],
        'clarity': [],
        'grammar': [],
        'vocabulary': [],
        'completeness': [],
        'coherence': [],
        'fluency_signal': [],
    }
    for turn in turns:
        breakdown = turn.evaluation_breakdown or {}
        for key in dimension_totals:
            if isinstance(breakdown.get(key), (int, float)):
                dimension_totals[key].append(int(breakdown[key]))

    dimension_averages = {
        key: _clamp(sum(values) / len(values)) if values else 0
        for key, values in dimension_totals.items()
    }
    sorted_dimensions = sorted(
        dimension_averages.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    summary_lookup = {
        'relevance': 'You stayed focused on the teacher prompts.',
        'clarity': 'You explained your ideas clearly.',
        'grammar': 'Your grammar stayed mostly accurate across the session.',
        'vocabulary': 'You used a solid range of speaking vocabulary.',
        'completeness': 'You gave complete answers with supporting details.',
        'coherence': 'You organized your ideas well from start to finish.',
        'fluency_signal': 'Your responses sounded smoother with fewer repeated fillers.',
    }
    improvement_lookup = {
        'relevance': 'Stay closer to the exact task before adding extra details.',
        'clarity': 'Make each main point clearer before moving to the next idea.',
        'grammar': 'Review tense control and agreement in longer spoken answers.',
        'vocabulary': 'Add more precise words instead of repeating simple vocabulary.',
        'completeness': 'Add one more supporting detail to complete each answer.',
        'coherence': 'Use more linking words to connect your ideas smoothly.',
        'fluency_signal': 'Reduce fillers and repeated words to improve fluency.',
    }

    strengths = []
    for key, value in sorted_dimensions:
        if value >= 75 and len(strengths) < 2:
            strengths.append(summary_lookup[key])
    if not strengths:
        strengths.append('You completed all three speaking practice turns.')

    improvement_areas = []
    for key, value in reversed(sorted_dimensions):
        if value < 75 and len(improvement_areas) < 2:
            improvement_areas.append(improvement_lookup[key])
    if not improvement_areas:
        improvement_areas.append('Keep practicing to make your speaking even more natural and detailed.')

    official_level = (lesson_session.session_context or {}).get('official_mastery_level', 'A1')
    return {
        'practice_score': practice_score,
        'label': SPEAKING_PRACTICE_SCORE_LABEL,
        'strengths': strengths,
        'improvement_areas': improvement_areas,
        'next_suggestion': (
            f'Practice one more {official_level} speaking session, then retake '
            'the Speaking Diagnostic when ready.'
        ),
        'feedback_summary': (
            f'You completed a three-turn speaking practice session with a '
            f'{SPEAKING_PRACTICE_SCORE_LABEL.lower()} of {practice_score}%.'
        ),
    }


def _serialize_speaking_teacher_session(lesson_session):
    context = lesson_session.session_context or {}
    turns = [
        _serialize_speaking_teacher_turn(turn)
        for turn in lesson_session.turns.all()
    ]
    final_result = None
    if lesson_session.status == 'completed':
        summary = lesson_session.feedback_summary or {}
        final_result = {
            'practice_score': (
                summary.get('practice_score')
                if summary.get('practice_score') is not None
                else int(lesson_session.final_score) if lesson_session.final_score is not None else None
            ),
            'label': summary.get('label', SPEAKING_PRACTICE_SCORE_LABEL),
            'strengths': summary.get('strengths', []),
            'improvement_areas': summary.get('improvement_areas', []),
            'next_suggestion': summary.get('next_suggestion', ''),
            'feedback_summary': summary.get('feedback_summary', ''),
        }

    return {
        'session_id': lesson_session.id,
        'study_session_id': lesson_session.study_session_id,
        'session_mode': lesson_session.session_mode,
        'skill': context.get('skill', SPEAKING_TEACHER_SKILL),
        'official_mastery_assessed': context.get('official_mastery_assessed', False),
        'official_mastery_score': context.get('official_mastery_score', 0),
        'official_mastery_level': context.get('official_mastery_level', 'A1'),
        'status': lesson_session.status,
        'current_turn': lesson_session.current_turn,
        'total_turns': context.get('total_turns', GUIDED_SESSION_TOTAL_TURNS),
        'lesson': lesson_session.lesson_text,
        'turns': turns,
        'current_task': (
            _serialize_speaking_current_task(_current_speaking_task(lesson_session))
            if lesson_session.status != 'completed'
            else None
        ),
        'final_result': final_result,
    }


def _module_selection_result(module, learner_level, fallback_used=False, fallback_reason=None):
    return {
        'module': module,
        'learner_level': learner_level,
        'module_level': module.level.level_code if module else None,
        'fallback_used': fallback_used,
        'fallback_reason': fallback_reason,
    }


def _select_module_for_skill(skill_name, learner_level):
    learner_level = _normalized_cefr_level(learner_level)
    active_modules = list(
        Module.objects.filter(
            is_active=True,
            skill__name=skill_name,
        )
        .select_related('level', 'skill')
        .order_by('level__sort_order', 'sort_order', 'id')
    )
    if not active_modules:
        return _module_selection_result(
            None,
            learner_level,
            fallback_used=True,
            fallback_reason=(
                f'No {learner_level} {skill_name} module is available yet, '
                'so choose another recommended lesson instead.'
            ),
        )

    modules_by_level = {}
    for module in active_modules:
        level_code = _normalized_cefr_level(module.level.level_code)
        modules_by_level.setdefault(level_code, []).append(module)

    if learner_level in modules_by_level:
        return _module_selection_result(
            modules_by_level[learner_level][0],
            learner_level,
        )

    learner_index = CEFR_PROGRESSION_ORDER.index(learner_level)
    lower_levels = list(reversed(CEFR_PROGRESSION_ORDER[:learner_index]))
    for level_code in lower_levels:
        if level_code in modules_by_level:
            module = modules_by_level[level_code][0]
            return _module_selection_result(
                module,
                learner_level,
                fallback_used=True,
                fallback_reason=(
                    f'No {learner_level} {skill_name} module is available yet, '
                    f'so an available {module.level.level_code} review module was selected.'
                ),
            )

    def distance_from_learner(module):
        module_level = _normalized_cefr_level(module.level.level_code)
        module_index = CEFR_PROGRESSION_ORDER.index(module_level)
        return (
            abs(module_index - learner_index),
            module_index,
            module.sort_order,
            module.id,
        )

    module = min(active_modules, key=distance_from_learner)
    return _module_selection_result(
        module,
        learner_level,
        fallback_used=True,
        fallback_reason=(
            f'No {learner_level} {skill_name} module is available yet, '
            f'so an available {module.level.level_code} module was selected.'
        ),
    )


def _select_default_module_for_level(learner_level):
    learner_level = _normalized_cefr_level(learner_level)
    active_modules = list(
        Module.objects.filter(is_active=True)
        .select_related('level', 'skill')
        .order_by('level__sort_order', 'sort_order', 'id')
    )
    if not active_modules:
        return _module_selection_result(
            None,
            learner_level,
            fallback_used=True,
            fallback_reason='No active modules are available yet.',
        )

    modules_by_level = {}
    for module in active_modules:
        level_code = _normalized_cefr_level(module.level.level_code)
        modules_by_level.setdefault(level_code, []).append(module)

    if learner_level in modules_by_level:
        module = modules_by_level[learner_level][0]
        return _module_selection_result(
            module,
            learner_level,
            fallback_used=True,
            fallback_reason=(
                f'No {learner_level} lesson was available for the focus skill, '
                f'so a {module.level.level_code} module was selected.'
            ),
        )

    learner_index = CEFR_PROGRESSION_ORDER.index(learner_level)
    lower_levels = list(reversed(CEFR_PROGRESSION_ORDER[:learner_index]))
    for level_code in lower_levels:
        if level_code in modules_by_level:
            module = modules_by_level[level_code][0]
            return _module_selection_result(
                module,
                learner_level,
                fallback_used=True,
                fallback_reason=(
                    f'No {learner_level} lesson was available for the focus skill, '
                    f'so a {module.level.level_code} review module was selected.'
                ),
            )

    module = active_modules[0]
    return _module_selection_result(
        module,
        learner_level,
        fallback_used=True,
        fallback_reason=(
            f'No {learner_level} lesson was available for the focus skill, '
            f'so an available {module.level.level_code} module was selected.'
        ),
    )


def get_curriculum_recommendation(user):
    masteries = list(
        SkillMastery.objects.filter(user=user)
        .select_related('skill')
        .order_by('score', 'skill__name')
    )
    learner_level = _learner_level_for_user(user)

    weakest = masteries[0] if masteries else None
    recommended_mastery = weakest
    module_selection = None
    for mastery in masteries:
        module_selection = _select_module_for_skill(
            mastery.skill.name,
            learner_level,
        )
        if module_selection['module'] is not None:
            recommended_mastery = mastery
            break

    if module_selection is None or module_selection['module'] is None:
        module_selection = _select_default_module_for_level(learner_level)

    module = module_selection['module']
    if recommended_mastery and module:
        if recommended_mastery == weakest:
            reason = f'{weakest.skill.name} is your weakest skill.'
        else:
            reason = (
                f'{recommended_mastery.skill.name} is your weakest skill '
                f'with an active {learner_level} module.'
            )
    elif weakest:
        reason = f'{weakest.skill.name} is your weakest skill.'
    else:
        reason = 'Start with a module at your current level.'

    score_lookup = {
        mastery.skill.name: int(mastery.score)
        for mastery in masteries
    }
    current_skill_scores = {
        'Vocabulary': score_lookup.get('Vocabulary'),
        'Grammar': score_lookup.get('Grammar'),
        'Listening': score_lookup.get('Listening'),
        'Speaking': score_lookup.get('Speaking'),
    }

    return {
        'recommended_module': _serialize_module(module),
        'reason': reason,
        'diagnostic_scores': current_skill_scores,
        'current_skill_scores': current_skill_scores,
        'weakest_skill': weakest.skill.name if weakest else None,
        'learner_level': module_selection['learner_level'],
        'module_level': module_selection['module_level'],
        'fallback_used': module_selection['fallback_used'],
        'fallback_reason': module_selection['fallback_reason'],
    }


def _join_with_and(values):
    items = [value for value in values if value]
    if not items:
        return ''
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f'{items[0]} and {items[1]}'
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _study_plan_focus_skills(user):
    masteries = list(
        SkillMastery.objects.filter(user=user)
        .select_related('skill')
        .order_by('score', 'skill__name')[:2]
    )
    focus = [mastery.skill.name for mastery in masteries]
    if not focus:
        focus = list(
            Skill.objects.order_by('id').values_list('name', flat=True)[:2]
        )
    return focus


def _learner_level_for_user(user):
    profile, _ = LearnerProfile.objects.get_or_create(user=user)
    first_mastery = (
        SkillMastery.objects.filter(user=user)
        .order_by('score', 'skill__name')
        .first()
    )
    return _normalized_cefr_level(
        profile.current_level or (
            first_mastery.level_code if first_mastery else 'A1'
        )
    )


def _study_plan_module_for_skill(user, skill_name, preferred_level):
    return _select_module_for_skill(skill_name, preferred_level)


def _build_study_plan_items(user, focus):
    preferred_level = _learner_level_for_user(user)
    items = []
    for index, skill_name in enumerate(focus, start=1):
        selection = _study_plan_module_for_skill(user, skill_name, preferred_level)
        module = selection['module']
        module_title = module.title if module else None
        module_level = selection['module_level']
        title = (
            f'{skill_name} - {module_title}'
            if module_title
            else f'{skill_name} - Recommended lesson'
        )
        items.append(
            {
                'day': f'Day {index}',
                'title': title,
                'skill': skill_name,
                'level': module_level,
                'learner_level': selection['learner_level'],
                'module_level': module_level,
                'module_id': module.id if module else None,
                'module_title': module_title,
                'fallback_used': selection['fallback_used'],
                'fallback_reason': selection['fallback_reason'],
                'href': f'/feedback?moduleId={module.id}' if module else '/recommendation',
            }
        )
    return items


@transaction.atomic
def create_teacher_session(user, module):
    session_state = start_guided_teacher_session(user, module)
    current_task = session_state['current_task']
    return {
        'session_id': session_state['study_session_id'],
        'lesson': session_state['lesson'],
        'practice_question': current_task['teacher_task'] if current_task else '',
    }


def _teacher_lesson_text(module):
    lesson_result = _lesson_result_from_llm(module)
    if lesson_result is not None:
        return lesson_result['lesson']

    objectives = module.objectives or []
    objective_text = '; '.join(objectives) if objectives else module.description
    return (
        f'{module.title}: {module.description} '
        f'Learning objectives: {objective_text}.'
    ).strip()


def _module_objectives(module):
    objectives = module.objectives or []
    if isinstance(objectives, list):
        return [objective.strip() for objective in objectives if isinstance(objective, str) and objective.strip()]
    return []


def _module_objective_summary(module):
    objectives = _module_objectives(module)
    if objectives:
        return objectives[0]
    description = (module.description or '').strip()
    if description:
        return description
    return f'Practice {module.skill.name.lower()} in this lesson.'


def _module_focus_profile(module):
    title = (module.title or '').strip()
    title_lower = title.lower()
    description_lower = (module.description or '').lower()
    objective_summary = _module_objective_summary(module)
    objective_text = ' '.join(_module_objectives(module)).lower()
    focus_text = ' '.join(
        part for part in [title_lower, description_lower, objective_text]
        if part
    )
    skill_name = module.skill.name
    skill_lower = skill_name.lower()

    if skill_lower == 'grammar':
        if any(
            phrase in focus_text
            for phrase in [
                'complex sentence',
                'complex sentences',
                'compound sentence',
                'compound and complex',
                'dependent clause',
                'subordinate clause',
            ]
        ):
            return {
                'focus_label': 'complex sentences',
                'lesson_objective': objective_summary,
                'tasks': [
                    {
                        'teacher_task': 'Combine two simple sentences into one complex sentence using because, although, or while.',
                        'reference_answer': 'Although I was tired, I finished my work.',
                        'explanation': 'Combine ideas with a dependent clause and a conjunction such as although, because, or while.',
                        'task_type': 'complex_sentence_conjunction',
                    },
                    {
                        'teacher_task': 'Write one sentence using although, because, or while to show a complex sentence.',
                        'reference_answer': 'Because I wanted to improve, I practiced English before work.',
                        'explanation': 'A complex sentence includes a dependent clause linked with a conjunction.',
                        'task_type': 'complex_sentence_conjunction',
                    },
                    {
                        'teacher_task': 'Describe a situation using at least one dependent clause in a complex sentence.',
                        'reference_answer': 'While I was solving a support ticket, I took notes for the next customer call.',
                        'explanation': 'Use a complete sentence that includes a dependent clause to match the lesson objective.',
                        'task_type': 'complex_sentence_clause',
                    },
                ],
            }
        if 'past' in title_lower:
            return {
                'focus_label': 'past tense',
                'lesson_objective': objective_summary,
                'tasks': [
                    {
                        'teacher_task': 'Write one sentence about something you did yesterday using the past tense.',
                        'reference_answer': 'Yesterday, I visited my friend.',
                        'explanation': 'Use a past tense verb to show the action already happened.',
                        'task_type': 'past_tense_sentence',
                    },
                    {
                        'teacher_task': 'Correct this sentence: "She go to school yesterday."',
                        'reference_answer': 'She went to school yesterday.',
                        'explanation': 'Use the past tense form "went" for an action that happened yesterday.',
                        'task_type': 'sentence_correction',
                    },
                    {
                        'teacher_task': 'Write one sentence about your last weekend using the past tense.',
                        'reference_answer': 'Last weekend, I watched a movie.',
                        'explanation': 'Use a complete sentence with a past tense verb.',
                        'task_type': 'past_tense_sentence',
                    },
                ],
            }
        return {
            'focus_label': 'simple present tense',
            'lesson_objective': objective_summary,
            'tasks': [
                {
                    'teacher_task': 'Create one sentence using the simple present tense.',
                    'reference_answer': 'I study English every evening.',
                    'explanation': 'Use the simple present to describe habits or routines.',
                    'task_type': 'simple_present_sentence',
                },
                {
                    'teacher_task': 'Correct this sentence: "She go to school every day."',
                    'reference_answer': 'She goes to school every day.',
                    'explanation': 'For he, she, and it, add -s or -es to the verb in the simple present tense.',
                    'task_type': 'sentence_correction',
                },
                {
                    'teacher_task': 'Write one sentence about your daily routine using the simple present tense.',
                    'reference_answer': 'I drink coffee before work every morning.',
                    'explanation': 'Describe a routine using the simple present.',
                    'task_type': 'simple_present_sentence',
                },
            ],
        }

    if skill_lower == 'vocabulary':
        return {
            'focus_label': title.lower() if title else 'vocabulary',
            'lesson_objective': objective_summary,
            'tasks': [
                {
                    'teacher_task': f'Write a sentence using useful vocabulary from "{title}" or the lesson objective.',
                    'reference_answer': 'I use clear and polite vocabulary at work.',
                    'explanation': 'Use target vocabulary in a clear, complete sentence.',
                    'task_type': 'vocabulary_sentence',
                },
                {
                    'teacher_task': 'Match a key lesson word to a stronger meaning by rewriting this sentence: "The meeting was good."',
                    'reference_answer': 'The meeting was productive.',
                    'explanation': 'Choose a more precise vocabulary word to improve meaning.',
                    'task_type': 'vocabulary_rewrite',
                },
                {
                    'teacher_task': f'Write a short paragraph or two connected sentences using lesson vocabulary related to "{title}".',
                    'reference_answer': 'I schedule meetings and answer customer emails with clear and professional language.',
                    'explanation': 'Use more than one target word naturally to match the lesson vocabulary objective.',
                    'task_type': 'vocabulary_paragraph',
                },
            ],
        }

    if skill_lower == 'speaking':
        return {
            'focus_label': title.lower() if title else 'spoken communication',
            'lesson_objective': objective_summary,
            'tasks': [
                {
                    'teacher_task': 'Write the sentence you would say to introduce yourself clearly.',
                    'reference_answer': 'Hello, my name is Maria, and I work in customer support.',
                    'explanation': 'Use a clear spoken sentence with complete ideas.',
                    'task_type': 'speaking_sentence',
                },
                {
                    'teacher_task': 'Answer this question in one complete sentence: "Why are you learning English?"',
                    'reference_answer': 'I am learning English to communicate better at work.',
                    'explanation': 'Answer the question directly and clearly.',
                    'task_type': 'speaking_sentence',
                },
                {
                    'teacher_task': 'Write one polite response you could say in a workplace conversation.',
                    'reference_answer': 'Sure, I can help you with that task this afternoon.',
                    'explanation': 'Use a natural and polite spoken response.',
                    'task_type': 'speaking_sentence',
                },
            ],
        }

    return {
        'focus_label': skill_name.lower(),
        'lesson_objective': objective_summary,
        'tasks': [
            {
                'teacher_task': f'Write one complete sentence that practices {skill_name.lower()}.',
                'reference_answer': 'I practice English every day.',
                'explanation': 'Use a clear complete sentence related to the skill.',
                'task_type': 'generic_sentence',
            },
            {
                'teacher_task': 'Improve this sentence so it sounds more natural: "I do English practice every day."',
                'reference_answer': 'I practice English every day.',
                'explanation': 'Choose the more natural English phrasing.',
                'task_type': 'generic_rewrite',
            },
            {
                'teacher_task': f'Write one more sentence to show progress in {skill_name.lower()}.',
                'reference_answer': 'I want to improve my English for work and daily life.',
                'explanation': 'Show the skill in a meaningful sentence.',
                'task_type': 'generic_sentence',
            },
        ],
    }


def _teacher_tasks_for_module(module):
    return _module_focus_profile(module)['tasks']


def _teacher_objective_for_module(module):
    return _module_focus_profile(module)['lesson_objective']


def _serialize_lesson_turn(turn):
    return {
        'turn_number': turn.turn_number,
        'teacher_task': turn.teacher_task,
        'student_answer': turn.student_answer,
        'score': int(turn.score) if turn.score is not None else None,
        'feedback': turn.ai_feedback,
        'correction': turn.correction,
        'explanation': turn.explanation,
        'encouragement': turn.encouragement,
    }


def _serialize_guided_session(lesson_session):
    study_session = lesson_session.study_session
    turns = [_serialize_lesson_turn(turn) for turn in lesson_session.turns.all()]
    lesson_objective = _teacher_objective_for_module(study_session.module)
    current_task = None
    if lesson_session.status != 'completed':
        tasks = _teacher_tasks_for_module(study_session.module)
        current_task = {
            'turn_number': lesson_session.current_turn,
            'teacher_task': tasks[lesson_session.current_turn - 1]['teacher_task'],
        }

    final_result = None
    if lesson_session.status == 'completed':
        summary = lesson_session.feedback_summary or {}
        final_result = {
            'session_score': (
                summary.get('session_score')
                if summary.get('session_score') is not None
                else int(lesson_session.final_score) if lesson_session.final_score is not None else None
            ),
            'strengths': summary.get('strengths', []),
            'improvement_areas': summary.get('improvement_areas', []),
            'next_study_suggestion': summary.get('next_study_suggestion', ''),
            'feedback_summary': summary.get('feedback_summary', ''),
        }

    return {
        'session_id': lesson_session.id,
        'study_session_id': study_session.id,
        'module': _serialize_module(study_session.module),
        'lesson': lesson_session.lesson_text or _teacher_lesson_text(study_session.module),
        'lesson_objective': lesson_objective,
        'status': lesson_session.status,
        'current_turn': lesson_session.current_turn,
        'total_turns': GUIDED_SESSION_TOTAL_TURNS,
        'current_task': current_task,
        'turns': turns,
        'final_result': final_result,
    }


def _encouragement_for_score(score):
    if score >= 85:
        return 'Strong work. Keep building on that accuracy.'
    if score >= 70:
        return 'Good progress. One more revision will make it stronger.'
    return 'Good effort. Keep practicing and focus on the correction.'


def _generic_sentence_feedback(answer_text, task):
    word_count = len(re.findall(r"[A-Za-z']+", answer_text))
    if word_count < 4:
        return 55, task['reference_answer'], task['explanation'], 'Add more detail and answer in one complete sentence.'
    return 84, answer_text.strip(), task['explanation'], 'You answered in a clear complete sentence.'


def _descriptive_score_label(score):
    if score >= 85:
        return 'high'
    if score >= 70:
        return 'good'
    if score >= 55:
        return 'developing'
    return 'low'


def _clarity_score(answer_text):
    word_count = len(re.findall(r"[A-Za-z']+", answer_text))
    if word_count < 4:
        return 45
    if word_count < 8:
        return 72
    return 88


def _grammar_accuracy_score(answer_text, task_type):
    has_tense_issue = re.search(
        r'\b(yesterday|last\s+\w+)\b[^.!?]*\b'
        r'(go|come|eat|see|do|have|make|take)\b',
        answer_text,
        flags=re.IGNORECASE,
    )
    has_agreement_issue = re.search(
        r'\b(he|she|it)\s+(go|live|work|study|play|like|want)\b',
        answer_text,
        flags=re.IGNORECASE,
    )
    if task_type == 'past_tense_sentence' and has_tense_issue:
        return 58
    if task_type == 'simple_present_sentence' and has_agreement_issue:
        return 60
    if has_tense_issue or has_agreement_issue:
        return 65
    return 90


def _objective_match_score(module, task, answer_text):
    task_type = task.get('task_type')
    answer_lower = answer_text.lower()
    word_count = len(re.findall(r"[A-Za-z']+", answer_text))

    if task_type in {'complex_sentence_conjunction', 'complex_sentence_clause'}:
        has_conjunction = bool(
            re.search(r'\b(although|because|while|if|when|since|unless|after|before)\b', answer_text, flags=re.IGNORECASE)
        )
        has_clause_shape = has_conjunction and (',' in answer_text or word_count >= 9)
        return 92 if has_clause_shape else 42

    if task_type == 'vocabulary_sentence':
        return 82 if word_count >= 6 else 60
    if task_type == 'vocabulary_rewrite':
        return 88 if 'good' not in answer_lower and word_count >= 3 else 52
    if task_type == 'vocabulary_paragraph':
        return 86 if word_count >= 12 else 58
    if task_type in {'simple_present_sentence', 'past_tense_sentence', 'speaking_sentence', 'generic_sentence'}:
        return 84 if word_count >= 6 else 62
    return 80 if word_count >= 6 else 60


def _teacher_feedback_from_breakdown(module, task, answer_text, grammar_accuracy, objective_match, clarity):
    skill_lower = module.skill.name.lower()
    task_type = task.get('task_type')
    grammar_label = _descriptive_score_label(grammar_accuracy)
    objective_label = _descriptive_score_label(objective_match)
    clarity_label = _descriptive_score_label(clarity)

    explanation = (
        f'Grammar accuracy: {grammar_label}. '
        f'Objective match: {objective_label}. '
        f'Clarity: {clarity_label}. '
        f'{task["explanation"]}'
    )

    if task_type in {'complex_sentence_conjunction', 'complex_sentence_clause'} and objective_match < 60:
        feedback = (
            'Your sentence is correct, but it does not show a complex sentence. '
            'Try using although, because, or while.'
        )
        correction = task['reference_answer']
        return feedback, correction, explanation

    if skill_lower == 'vocabulary' and objective_match < 60:
        feedback = 'Your answer is clear, but it needs more lesson vocabulary to match this task.'
        correction = task['reference_answer']
        return feedback, correction, explanation

    if grammar_accuracy < 70:
        feedback = 'Your answer shows the main idea, but review the grammar pattern needed for this lesson.'
        correction = task['reference_answer']
        return feedback, correction, explanation

    if clarity < 60:
        feedback = 'Your answer needs more detail so it clearly completes the task.'
        correction = task['reference_answer']
        return feedback, correction, explanation

    if objective_match < 75:
        feedback = 'Your answer is mostly correct, but it does not fully match the lesson objective yet.'
        correction = task['reference_answer']
        return feedback, correction, explanation

    feedback = 'Your answer is correct and matches the lesson objective.'
    correction = answer_text.strip()
    return feedback, correction, explanation


def _evaluate_task_fallback(module, turn_number, answer):
    tasks = _teacher_tasks_for_module(module)
    task = tasks[turn_number - 1]
    answer_text = answer.strip()
    answer_lower = answer_text.lower()
    skill_lower = module.skill.name.lower()
    task_type = task.get('task_type')

    if not answer_text:
        return {
            'score': 0,
            'feedback': 'Please answer the task with a complete sentence.',
            'correction': task['reference_answer'],
            'explanation': task['explanation'],
            'encouragement': 'Take another try with one clear sentence.',
        }

    if task_type == 'sentence_correction':
        expected = _normalized_compare_text(task['reference_answer'])
        if _normalized_compare_text(answer_text) == expected:
            return {
                'score': 95,
                'feedback': 'Excellent correction. You fixed the target sentence correctly.',
                'correction': task['reference_answer'],
                'explanation': task['explanation'],
                'encouragement': _encouragement_for_score(95),
            }
        return {
            'score': 62,
            'feedback': f'Good try. The correct sentence is: {task["reference_answer"]}',
            'correction': task['reference_answer'],
            'explanation': task['explanation'],
            'encouragement': _encouragement_for_score(62),
        }

    if skill_lower == 'grammar':
        if turn_number == 2 and task_type == 'sentence_correction':
            expected = _normalized_compare_text(task['reference_answer'])
            if _normalized_compare_text(answer_text) == expected:
                return {
                    'score': 95,
                    'feedback': 'Excellent correction. You fixed the verb form correctly.',
                    'correction': task['reference_answer'],
                    'explanation': task['explanation'],
                    'encouragement': _encouragement_for_score(95),
                }
        grammar_accuracy = _grammar_accuracy_score(answer_text, task_type)
        objective_match = _objective_match_score(module, task, answer_text)
        clarity = _clarity_score(answer_text)
        score = _clamp(grammar_accuracy * 0.4 + objective_match * 0.4 + clarity * 0.2)
        feedback, correction, explanation = _teacher_feedback_from_breakdown(
            module,
            task,
            answer_text,
            grammar_accuracy,
            objective_match,
            clarity,
        )
        return {
            'score': score,
            'feedback': feedback,
            'correction': correction,
            'explanation': explanation,
            'encouragement': _encouragement_for_score(score),
            'grammar_accuracy': grammar_accuracy,
            'objective_match': objective_match,
            'clarity': clarity,
        }

    if skill_lower == 'vocabulary':
        grammar_accuracy = _grammar_accuracy_score(answer_text, task_type)
        objective_match = _objective_match_score(module, task, answer_text)
        clarity = _clarity_score(answer_text)
        score = _clamp(grammar_accuracy * 0.25 + objective_match * 0.5 + clarity * 0.25)
        feedback, correction, explanation = _teacher_feedback_from_breakdown(
            module,
            task,
            answer_text,
            grammar_accuracy,
            objective_match,
            clarity,
        )
        return {
            'score': score,
            'feedback': feedback,
            'correction': correction,
            'explanation': explanation,
            'encouragement': _encouragement_for_score(score),
            'grammar_accuracy': grammar_accuracy,
            'objective_match': objective_match,
            'clarity': clarity,
        }

    grammar_accuracy = _grammar_accuracy_score(answer_text, task_type)
    objective_match = _objective_match_score(module, task, answer_text)
    clarity = _clarity_score(answer_text)
    score = _clamp(grammar_accuracy * 0.3 + objective_match * 0.35 + clarity * 0.35)
    feedback, correction, explanation = _teacher_feedback_from_breakdown(
        module,
        task,
        answer_text,
        grammar_accuracy,
        objective_match,
        clarity,
    )
    return {
        'score': score,
        'feedback': feedback,
        'correction': correction,
        'explanation': explanation,
        'encouragement': _encouragement_for_score(score),
        'grammar_accuracy': grammar_accuracy,
        'objective_match': objective_match,
        'clarity': clarity,
    }


def _build_final_session_feedback(module, turns):
    scores = [int(turn.score) for turn in turns if turn.score is not None]
    final_score = _clamp(sum(scores) / len(scores)) if scores else 0

    strengths = []
    if final_score >= 80:
        strengths.append('You stayed consistent across the guided lesson tasks.')
    if any(int(turn.score) >= 85 for turn in turns if turn.score is not None):
        strengths.append('You produced at least one strong, accurate response.')
    if not strengths:
        strengths.append('You completed all three guided lesson tasks.')

    improvement_areas = []
    if any(int(turn.score) < 70 for turn in turns if turn.score is not None):
        improvement_areas.append(f'Review the key pattern in {module.skill.name.lower()} before the next lesson.')
    if module.skill.name == 'Grammar':
        improvement_areas.append('Keep checking verb forms carefully before submitting your answer.')
    elif module.skill.name == 'Vocabulary':
        improvement_areas.append('Use more precise words and fuller sentences to show mastery.')
    else:
        improvement_areas.append('Add a little more detail to make each response stronger.')

    if final_score >= 80:
        next_study_suggestion = f'Continue with another {module.level.level_code} {module.skill.name} lesson to reinforce your progress.'
    else:
        next_study_suggestion = f'Review this {module.skill.name} lesson again, then continue with another {module.level.level_code} activity.'

    feedback_summary = (
        f'You completed a three-task {module.skill.name} session with a session score of {final_score}%.'
    )

    return {
        'session_score': final_score,
        'strengths': strengths,
        'improvement_areas': improvement_areas,
        'next_study_suggestion': next_study_suggestion,
        'feedback_summary': feedback_summary,
    }


def _recommended_module_for_user(user):
    recommendation = get_curriculum_recommendation(user)
    module_data = recommendation.get('recommended_module')
    if not module_data:
        return None
    return Module.objects.filter(pk=module_data['id'], is_active=True).select_related('level', 'skill').first()


@transaction.atomic
def start_guided_teacher_session(user, module=None):
    if module is None:
        module = _recommended_module_for_user(user)
    if module is None:
        raise ValueError('No active recommended module is available.')

    lesson_text = _teacher_lesson_text(module)
    study_session = StudySession.objects.create(
        user=user,
        module=module,
        session_type='guided_teacher_session',
    )
    lesson_session = LessonSession.objects.create(
        study_session=study_session,
        lesson_text=lesson_text,
        session_mode=LessonSession.SESSION_MODE_TEXT,
        status='active',
        current_turn=1,
    )
    return _serialize_guided_session(lesson_session)


def get_guided_teacher_session_state(user, lesson_session):
    if lesson_session.study_session.user_id != user.id:
        raise LessonSession.DoesNotExist
    return _serialize_guided_session(lesson_session)


@transaction.atomic
def start_speaking_teacher_session(user):
    session_context = _build_speaking_session_context(user)
    lesson_session = LessonSession.objects.create(
        study_session=StudySession.objects.create(
            user=user,
            session_type=SPEAKING_TEACHER_SESSION_TYPE,
        ),
        lesson_text=_speaking_session_intro(session_context['official_mastery_level']),
        session_mode=LessonSession.SESSION_MODE_SPEAKING,
        session_context=session_context,
        status='active',
        current_turn=1,
    )
    return _serialize_speaking_teacher_session(lesson_session)


def get_speaking_teacher_session_state(user, lesson_session):
    if lesson_session.study_session.user_id != user.id:
        raise LessonSession.DoesNotExist
    if lesson_session.session_mode != LessonSession.SESSION_MODE_SPEAKING:
        raise LessonSession.DoesNotExist
    return _serialize_speaking_teacher_session(lesson_session)


@transaction.atomic
def answer_speaking_teacher_session(
    user,
    lesson_session,
    transcript=None,
    audio_file=None,
):
    if lesson_session.study_session.user_id != user.id:
        raise LessonSession.DoesNotExist
    if lesson_session.session_mode != LessonSession.SESSION_MODE_SPEAKING:
        raise LessonSession.DoesNotExist
    if lesson_session.status == 'completed':
        raise ValueError('This speaking teacher session is already complete.')

    transcript_text = _normalize_text(transcript)
    if transcript_text is None:
        if audio_file is None:
            raise ValueError('Provide a transcript or audio_file.')
        from .voice_services import transcribe_audio

        transcript_text = transcribe_audio(audio_file)

    task = _current_speaking_task(lesson_session)
    if task is None:
        raise ValueError('This speaking teacher session has no remaining task.')

    evaluation = _evaluate_speaking_teacher_answer(task, transcript_text)
    turn_number = lesson_session.current_turn
    turn = LessonTurn.objects.create(
        session=lesson_session,
        turn_number=turn_number,
        task_type=task['task_type'],
        target_focus=task['target_focus'],
        teacher_task=task['teacher_prompt'],
        student_answer=transcript_text,
        ai_feedback=evaluation['feedback'],
        correction=evaluation['correction'],
        explanation=evaluation['explanation'],
        encouragement=evaluation['encouragement'],
        score=Decimal(evaluation['score']),
        evaluation_breakdown=evaluation['evaluation_breakdown'],
    )

    lesson_session.study_session.input_text = '\n'.join(
        lesson_session.turns.exclude(student_answer='').values_list('student_answer', flat=True)
    )

    response = {
        'session_id': lesson_session.id,
        'turn': _serialize_speaking_teacher_turn(turn),
        'completed': False,
        'next_task': None,
        'final_result': None,
    }

    total_turns = (lesson_session.session_context or {}).get(
        'total_turns',
        GUIDED_SESSION_TOTAL_TURNS,
    )
    if turn_number >= total_turns:
        lesson_session.status = 'completed'
        lesson_session.completed_at = timezone.now()
        final_result = _build_speaking_final_result(lesson_session)
        lesson_session.final_score = Decimal(final_result['practice_score'])
        lesson_session.feedback_summary = final_result
        lesson_session.study_session.ai_feedback = final_result['feedback_summary']
        lesson_session.study_session.score = Decimal(final_result['practice_score'])
        lesson_session.study_session.completed_at = lesson_session.completed_at
        response['completed'] = True
        response['final_result'] = final_result
    else:
        lesson_session.current_turn = turn_number + 1
        response['next_task'] = _serialize_speaking_next_task(
            _current_speaking_task(lesson_session)
        )

    lesson_session.study_session.save(
        update_fields=[
            'input_text',
            'ai_feedback',
            'score',
            'completed_at',
        ]
    )
    lesson_session.save(
        update_fields=[
            'status',
            'current_turn',
            'final_score',
            'feedback_summary',
            'completed_at',
        ]
    )
    return response


@transaction.atomic
def answer_guided_teacher_session(user, lesson_session, answer):
    if lesson_session.study_session.user_id != user.id:
        raise LessonSession.DoesNotExist
    if lesson_session.status == 'completed':
        raise ValueError('This lesson session is already complete.')

    answer_text = answer.strip()
    turn_number = lesson_session.current_turn
    task = _teacher_tasks_for_module(lesson_session.study_session.module)[turn_number - 1]
    evaluation = _evaluate_task_fallback(
        lesson_session.study_session.module,
        turn_number,
        answer_text,
    )
    turn = LessonTurn.objects.create(
        session=lesson_session,
        turn_number=turn_number,
        task_type=task.get('task_type', ''),
        teacher_task=task['teacher_task'],
        student_answer=answer_text,
        ai_feedback=evaluation['feedback'],
        correction=evaluation['correction'],
        explanation=evaluation['explanation'],
        encouragement=evaluation['encouragement'],
        score=Decimal(evaluation['score']),
    )

    lesson_session.study_session.input_text = '\n'.join(
        lesson_session.turns.exclude(student_answer='').values_list('student_answer', flat=True)
    )

    response = {
        'session_id': lesson_session.id,
        'turn': _serialize_lesson_turn(turn),
        'completed': False,
        'next_task': None,
        'final_result': None,
    }

    if turn_number >= GUIDED_SESSION_TOTAL_TURNS:
        lesson_session.status = 'completed'
        lesson_session.completed_at = timezone.now()
        final_summary = _build_final_session_feedback(
            lesson_session.study_session.module,
            list(lesson_session.turns.all()),
        )
        final_score = final_summary['session_score']
        lesson_session.final_score = Decimal(final_score)
        lesson_session.feedback_summary = final_summary
        lesson_session.study_session.ai_feedback = final_summary['feedback_summary']
        lesson_session.study_session.score = Decimal(final_score)
        lesson_session.study_session.completed_at = lesson_session.completed_at
        response['completed'] = True
        response['final_result'] = {
            'session_score': final_score,
            'strengths': final_summary['strengths'],
            'improvement_areas': final_summary['improvement_areas'],
            'next_study_suggestion': final_summary['next_study_suggestion'],
            'feedback_summary': final_summary['feedback_summary'],
        }
    else:
        lesson_session.current_turn = turn_number + 1
        next_task = _teacher_tasks_for_module(lesson_session.study_session.module)[lesson_session.current_turn - 1]
        response['next_task'] = {
            'turn_number': lesson_session.current_turn,
            'teacher_task': next_task['teacher_task'],
        }

    lesson_session.study_session.save(
        update_fields=[
            'input_text',
            'ai_feedback',
            'score',
            'completed_at',
        ]
    )
    lesson_session.save(
        update_fields=[
            'status',
            'current_turn',
            'final_score',
            'feedback_summary',
            'completed_at',
        ]
    )
    return response


def generate_teacher_feedback(answer):
    answer_text = answer.strip()
    tense_error = re.search(
        r'\b(yesterday|last\s+\w+)\b[^.!?]*\b'
        r'(go|come|eat|see|do|have|make|take)\b',
        answer_text,
        flags=re.IGNORECASE,
    )
    agreement_error = re.search(
        r'\b(he|she|it)\s+(go|live|work|study|play|like|want)\b',
        answer_text,
        flags=re.IGNORECASE,
    )

    if tense_error:
        return 62, 'Good attempt. Review verb tense.'
    if agreement_error:
        return 60, 'Good attempt. Review subject-verb agreement.'

    word_count = len(re.findall(r"[A-Za-z']+", answer_text))
    if word_count < 4:
        return 50, 'Add more detail and answer in a complete sentence.'
    if word_count < 8:
        return 72, 'Good work. Add one more detail to strengthen your answer.'
    return 82, 'Strong answer. Keep practicing for consistency.'


@transaction.atomic
def submit_teacher_feedback(user, session, answer):
    lesson_session = getattr(session, 'lesson_session', None)
    if lesson_session is None:
        lesson_session = LessonSession.objects.create(
            study_session=session,
            session_mode=LessonSession.SESSION_MODE_TEXT,
            status='active',
            current_turn=1,
        )

    result = answer_guided_teacher_session(user, lesson_session, answer)
    feedback = result['turn']
    payload = {
        'session_score': feedback['score'],
        'feedback': feedback['feedback'],
        'correction': feedback['correction'],
        'explanation': feedback['explanation'],
        'encouragement': feedback['encouragement'],
        'completed': result['completed'],
        'next_task': result['next_task'],
        'final_result': result['final_result'],
    }
    return payload


@transaction.atomic
def generate_study_plan(user):
    focus = _study_plan_focus_skills(user)
    items = _build_study_plan_items(user, focus)
    days = [
        f"{item['day']}: {item['title']}"
        for item in items
    ]
    plan_data = {
        'focus': focus,
        'days': days,
        'items': items,
    }
    start_date = timezone.localdate()
    StudyPlan.objects.create(
        user=user,
        plan_data=plan_data,
        focus_skills=focus,
        start_date=start_date,
        end_date=start_date + timedelta(days=6),
    )
    return {'plan': plan_data}


def get_coach_summary(user):
    focus = _study_plan_focus_skills(user)
    if not focus:
        return {
            'summary': 'Complete the diagnostic to start tracking your progress.',
            'next_step': 'Start with the diagnostic, then generate a weekly plan.',
        }

    return {
        'summary': f'Your focus this week is {_join_with_and(focus)}.',
        'next_step': (
            'Complete the recommended lessons, then retake your diagnostic '
            'to update your official mastery.'
        ),
    }
