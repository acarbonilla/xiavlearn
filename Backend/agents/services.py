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


def _diagnostic_result_from_llm(answers):
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

    weak_skills = _normalize_weak_skills(
        llm_payload.get('weak_skills'),
        skill_scores,
    )
    recommendation = _normalize_text(llm_payload.get('recommendation'))
    if recommendation is None:
        recommendation = f"Focus on {' and '.join(weak_skills)}."

    return {
        'overall_level': overall_level,
        'skill_scores': skill_scores,
        'weak_skills': weak_skills,
        'recommendation': recommendation,
    }


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


@transaction.atomic
def evaluate_diagnostic(user, answers):
    diagnostic_result = _diagnostic_result_from_llm(answers)
    if diagnostic_result is None:
        skill_scores = score_diagnostic_answers(answers)
        average_score = sum(skill_scores.values()) / len(skill_scores)
        overall_level = _level_for_score(average_score)
        weakest = sorted(skill_scores, key=lambda name: (skill_scores[name], name))[:2]
        diagnostic_result = {
            'overall_level': overall_level,
            'skill_scores': skill_scores,
            'weak_skills': weakest,
            'recommendation': f"Focus on {' and '.join(weakest)}.",
        }

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
