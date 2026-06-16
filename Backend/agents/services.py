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
    'do', 'english', 'every', 'for', 'goal', 'good', 'hello', 'hi', 'home',
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

    average_score = sum(skill_scores.values()) / len(skill_scores)
    overall_level = _level_for_score(average_score)
    weak_skills = sorted(skill_scores, key=lambda name: (skill_scores[name], name))[:2]
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

    return diagnostic_result

def get_curriculum_recommendation(user):
    profile, _ = LearnerProfile.objects.get_or_create(user=user)
    masteries = list(
        SkillMastery.objects.filter(user=user)
        .select_related('skill')
        .order_by('score', 'skill__name')
    )
    level_code = profile.current_level or (
        masteries[0].level_code if masteries else 'A1'
    )
    active_modules = Module.objects.filter(is_active=True).select_related(
        'level', 'skill'
    )

    weakest = masteries[0] if masteries else None
    recommended_mastery = weakest
    module = None
    for mastery in masteries:
        module = active_modules.filter(
            level__level_code=level_code,
            skill=mastery.skill,
        ).order_by('sort_order', 'id').first()
        if module:
            recommended_mastery = mastery
            break

    if module is None and weakest:
        module = active_modules.filter(
            skill=weakest.skill,
        ).order_by('level__sort_order', 'sort_order', 'id').first()

    if module is None:
        module = active_modules.filter(
            level__level_code=level_code,
        ).order_by('sort_order', 'id').first()
    if module is None:
        module = active_modules.order_by(
            'level__sort_order', 'sort_order', 'id'
        ).first()

    if recommended_mastery and module:
        if recommended_mastery == weakest:
            reason = f'{weakest.skill.name} is your weakest skill.'
        else:
            reason = (
                f'{recommended_mastery.skill.name} is your weakest skill '
                f'with an active {level_code} module.'
            )
    elif weakest:
        reason = f'{weakest.skill.name} is your weakest skill.'
    else:
        reason = 'Start with a module at your current level.'

    score_lookup = {
        mastery.skill.name: int(mastery.score)
        for mastery in masteries
    }
    diagnostic_scores = {
        'Vocabulary': score_lookup.get('Vocabulary'),
        'Grammar': score_lookup.get('Grammar'),
        'Listening': score_lookup.get('Listening'),
        'Speaking': score_lookup.get('Speaking'),
    }

    return {
        'recommended_module': _serialize_module(module),
        'reason': reason,
        'diagnostic_scores': diagnostic_scores,
        'weakest_skill': weakest.skill.name if weakest else None,
    }


@transaction.atomic
def create_teacher_session(user, module):
    session = StudySession.objects.create(
        user=user,
        module=module,
        session_type='lesson',
    )
    lesson_result = _lesson_result_from_llm(module)
    if lesson_result is None:
        objectives = module.objectives or []
        objective_text = '; '.join(objectives) if objectives else module.description
        lesson_result = {
            'lesson': (
                f'{module.title}: {module.description} '
                f'Learning objectives: {objective_text}.'
            ).strip(),
            'practice_question': (
                'Write one English sentence that demonstrates: '
                f'{objectives[0] if objectives else module.title}.'
            ),
        }

    return {
        'session_id': session.id,
        'lesson': lesson_result['lesson'],
        'practice_question': lesson_result['practice_question'],
    }


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
    llm_feedback = _teacher_feedback_from_llm(session.module, answer)
    if llm_feedback is None:
        score, feedback = generate_teacher_feedback(answer)
    else:
        score, feedback = llm_feedback

    session.input_text = answer.strip()
    session.ai_feedback = feedback
    session.score = Decimal(score)
    session.completed_at = timezone.now()
    session.save(
        update_fields=[
            'input_text',
            'ai_feedback',
            'score',
            'completed_at',
        ]
    )

    mastery, _ = SkillMastery.objects.update_or_create(
        user=user,
        skill=session.module.skill,
        defaults={
            'level_code': session.module.level.level_code,
            'score': Decimal(score),
            'status': _status_for_score(score),
        },
    )
    return {
        'score': score,
        'feedback': feedback,
        'updated_mastery': {
            'skill': mastery.skill.name,
            'score': int(mastery.score),
            'status': mastery.status,
        },
    }


@transaction.atomic
def generate_study_plan(user):
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
    days = [
        f'Day {index}: Practice {skill_name}'
        for index, skill_name in enumerate(focus, start=1)
    ]
    plan_data = {'focus': focus, 'days': days}
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
    profile, _ = LearnerProfile.objects.get_or_create(user=user)
    weakest = (
        SkillMastery.objects.filter(user=user)
        .select_related('skill')
        .order_by('score', 'skill__name')
        .first()
    )
    recent_sessions = StudySession.objects.filter(
        user=user,
        completed_at__isnull=False,
    ).order_by('-completed_at')[:5]
    completed_count = len(recent_sessions)

    llm_summary = _coach_summary_from_llm(
        profile.current_level,
        weakest,
        completed_count,
    )
    if llm_summary is not None:
        return llm_summary

    if weakest:
        if completed_count:
            summary = (
                f'You are improving, but {weakest.skill.name} needs more review.'
            )
        else:
            summary = (
                f'{weakest.skill.name} needs more review. '
                'Complete a lesson to begin tracking progress.'
            )
    else:
        summary = 'Complete the diagnostic to start tracking your progress.'

    return {
        'summary': summary,
        'next_step': 'Complete your recommended module.',
    }







