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
CEFR_LEVELS = {'A1', 'A2', 'B1', 'B2'}
SKILL_NAME_LOOKUP = {name.lower(): name for name in SKILL_NAMES}
MISTAKE_TYPES = {
    'grammar': 'Grammar',
    'spelling': 'Spelling',
    'vocabulary': 'Vocabulary',
    'clarity': 'Clarity',
    'sentence structure': 'Sentence Structure',
}
COMMON_WORDS = {
    'a', 'about', 'after', 'am', 'an', 'and', 'are', 'at', 'basic', 'be',
    'because', 'can', 'clear', 'communication', 'confidently', 'describe',
    'did', 'do', 'english', 'every', 'for', 'goal', 'good', 'hello', 'hi',
    'home', 'i', 'improve', 'in', 'introduce', 'is', 'it', 'learn',
    'learning', 'live', 'my', 'name', 'practice', 'school', 'sentence',
    'simple', 'speak', 'speaking', 'skills', 'studied', 'study', 'to',
    'want', 'was', 'what', 'yesterday', 'you', 'your'
}
SPELLING_HINTS = {
    'im': 'I am',
    'learng': 'learning',
    'lakkee': 'like',
    'hose': 'home',
}
QUESTION_CORRECTIONS = {
    'introduce yourself in english.': (
        'Hi, my name is [your name]. I am learning English to improve my communication skills.'
    ),
    'describe what you did yesterday.': (
        'Yesterday, I studied English and practiced speaking at home.'
    ),
    'what is your learning goal?': (
        'My learning goal is to speak English clearly and confidently.'
    ),
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


def _normalize_skill_scores(raw_scores):
    if not isinstance(raw_scores, dict):
        return None

    normalized_scores = {}
    for raw_name, raw_score in raw_scores.items():
        if not isinstance(raw_name, str) or not isinstance(raw_score, (int, float)):
            continue
        skill_name = SKILL_NAME_LOOKUP.get(raw_name.strip().lower())
        if skill_name is None:
            continue
        normalized_scores[skill_name] = _clamp(raw_score)

    if set(normalized_scores) != set(SKILL_NAMES):
        return None
    return normalized_scores


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
        if skill_name and skill_name not in seen:
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


def _normalize_answer_feedback(raw_feedback, answers):
    if not isinstance(raw_feedback, list) or len(raw_feedback) < len(answers):
        return None

    normalized_feedback = []
    for index, source_answer in enumerate(answers):
        item = raw_feedback[index]
        if not isinstance(item, dict):
            return None

        feedback = _normalize_text(item.get('feedback'))
        corrected_answer = _normalize_text(item.get('corrected_answer'))
        raw_mistakes = item.get('mistakes')
        if feedback is None or corrected_answer is None or not isinstance(raw_mistakes, list):
            return None

        mistakes = []
        for raw_mistake in raw_mistakes:
            normalized_mistake = _normalize_mistake(raw_mistake)
            if normalized_mistake is None:
                return None
            mistakes.append(normalized_mistake)

        normalized_feedback.append(
            {
                'question': _normalize_text(item.get('question'))
                or source_answer.get('question', '').strip(),
                'answer': _normalize_text(item.get('answer'))
                or source_answer.get('answer', '').strip(),
                'feedback': feedback,
                'corrected_answer': corrected_answer,
                'mistakes': mistakes,
            }
        )

    return normalized_feedback


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
    completion = metrics['completion_ratio']
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
        'Speaking': _clamp(
            38 + min(word_count * 1.5, 24) + completion * 6
        ),
        'Listening': _clamp(
            42 + completion * 12 + min(len(answers), 3) * 2
        ),
        'Pronunciation': _clamp(
            48 + min(word_count, 12) + completion * 3
        ),
    }


def _default_corrected_answer(question):
    return QUESTION_CORRECTIONS.get(
        question.strip().lower(),
        'I want to answer in clear and complete English sentences.'
    )


def _has_sentence_structure(words):
    lower_words = [word.lower() for word in words]
    has_subject = any(word in {'i', 'he', 'she', 'we', 'they', 'you', 'my'} for word in lower_words)
    has_verb = any(
        word in {
            'am', 'is', 'are', 'was', 'were', 'be', 'study', 'studied', 'learn',
            'learning', 'want', 'wanted', 'go', 'went', 'did', 'do', 'live', 'improve'
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


def _build_corrected_answer(question, answer, mistakes, is_unclear):
    if is_unclear:
        return _default_corrected_answer(question)

    corrected_answer = answer.strip()
    replacements = []
    for mistake in mistakes:
        original = mistake['original']
        correction = mistake['correction']
        if original.lower() == correction.lower():
            continue
        replacements.append((original, correction))

    for original, correction in replacements:
        corrected_answer = re.sub(
            re.escape(original),
            correction,
            corrected_answer,
            flags=re.IGNORECASE,
        )

    corrected_answer = corrected_answer.strip()
    if corrected_answer and corrected_answer[-1] not in '.!?':
        corrected_answer = f'{corrected_answer}.'
    if corrected_answer:
        return corrected_answer
    return _default_corrected_answer(question)


def _analyze_answer_feedback(question, answer):
    answer_text = answer.strip()
    question_lower = question.strip().lower()
    words = re.findall(r"[A-Za-z']+", answer_text)
    lower_words = [word.lower() for word in words]
    mistakes = []
    seen = set()
    tense_issue = False

    def add_mistake(mistake_type, original, correction, explanation):
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
        add_mistake(
            'Sentence Structure',
            '(empty answer)',
            _default_corrected_answer(question),
            'Use at least one complete sentence so the diagnostic can measure your level.',
        )
        return {
            'question': question.strip(),
            'answer': answer_text,
            'feedback': 'Your answer is missing. Write one clear complete sentence so the agent can evaluate your English.',
            'corrected_answer': _default_corrected_answer(question),
            'mistakes': mistakes,
            'is_unclear': True,
        }

    if re.search(r'\bim\b', answer_text, flags=re.IGNORECASE):
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

    word_count = len(words)
    unclear_ratio = len(suspicious_words) / max(word_count, 1)
    has_sentence_structure = _has_sentence_structure(words)
    is_unclear = (
        unclear_ratio >= 0.28
        or not has_sentence_structure
        or word_count < 4
        or lower_words.count('me') >= 2
        or (
            'introduce yourself' in question_lower
            and 'my name' not in answer_text.lower()
            and 'i am' not in answer_text.lower()
        )
    )

    if is_unclear:
        add_mistake(
            'Clarity',
            answer_text,
            _default_corrected_answer(question),
            'The original answer is unclear or incomplete, so it needs a clearer complete idea.',
        )

    if word_count < 6:
        add_mistake(
            'Sentence Structure',
            answer_text,
            _default_corrected_answer(question),
            'Use one or two complete sentences with a clear subject, verb, and idea.',
        )

    if is_unclear:
        feedback = (
            'Your answer uses some English words, but the meaning is unclear. '
            'You need clearer complete sentences with more accurate grammar and word choice.'
        )
    elif tense_issue and 'yesterday' in question_lower:
        feedback = (
            'Your answer gives the main idea, but you need past tense verbs to describe what happened yesterday correctly.'
        )
    elif mistakes:
        feedback = (
            'Your answer shows the main idea, but it still has grammar, spelling, or sentence structure problems that need correction.'
        )
    else:
        feedback = (
            'Your answer is clear and understandable. Keep adding detail to improve accuracy and fluency.'
        )

    corrected_answer = _build_corrected_answer(question, answer, mistakes, is_unclear)
    return {
        'question': question.strip(),
        'answer': answer_text,
        'feedback': feedback,
        'corrected_answer': corrected_answer,
        'mistakes': mistakes,
        'is_unclear': is_unclear,
    }


def _rule_based_level_explanation(overall_level, diagnostics):
    total_mistakes = sum(len(item['mistakes']) for item in diagnostics)
    unclear_answers = sum(1 for item in diagnostics if item['is_unclear'])

    if unclear_answers >= 2:
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
    total_issues = sum(len(item['mistakes']) for item in diagnostics)

    skill_scores = {
        'Grammar': _clamp(
            base_scores['Grammar']
            - grammar_issues * 10
            - structure_issues * 8
            - unclear_answers * 8
            - spelling_issues * 4
        ),
        'Vocabulary': _clamp(
            base_scores['Vocabulary']
            - clarity_issues * 8
            - spelling_issues * 6
            - unclear_answers * 6
        ),
        'Speaking': _clamp(
            base_scores['Speaking']
            - unclear_answers * 12
            - grammar_issues * 6
            - total_issues * 2
        ),
        'Listening': _clamp(
            base_scores['Listening']
            - unclear_answers * 10
            - total_issues * 2
        ),
        'Pronunciation': _clamp(
            base_scores['Pronunciation']
            - spelling_issues * 8
            - clarity_issues * 4
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

    skill_scores = _normalize_skill_scores(llm_payload.get('skill_scores'))
    if skill_scores is None:
        return None

    average_score = sum(skill_scores.values()) / len(skill_scores)
    overall_level = _normalize_text(llm_payload.get('overall_level'))
    if overall_level:
        overall_level = overall_level.upper()
    if overall_level not in CEFR_LEVELS:
        overall_level = _level_for_score(average_score)

    result = dict(fallback_result)
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
    result['answer_feedback'] = (
        _normalize_answer_feedback(llm_payload.get('answer_feedback'), answers)
        or fallback_result['answer_feedback']
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

    for skill_name in SKILL_NAMES:
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

    return {
        'recommended_module': _serialize_module(module),
        'reason': reason,
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
