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


SKILL_NAMES = [
    'Grammar',
    'Vocabulary',
    'Speaking',
    'Listening',
    'Pronunciation',
]


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
    skill_scores = score_diagnostic_answers(answers)
    average_score = sum(skill_scores.values()) / len(skill_scores)
    overall_level = _level_for_score(average_score)

    profile, _ = LearnerProfile.objects.get_or_create(user=user)
    profile.current_level = overall_level
    profile.save(update_fields=['current_level', 'updated_at'])

    for skill_name in SKILL_NAMES:
        skill, _ = Skill.objects.get_or_create(name=skill_name)
        score = skill_scores[skill_name]
        SkillMastery.objects.update_or_create(
            user=user,
            skill=skill,
            defaults={
                'level_code': overall_level,
                'score': Decimal(score),
                'status': _status_for_score(score),
            },
        )

    weakest = sorted(skill_scores, key=lambda name: (skill_scores[name], name))[:2]
    return {
        'overall_level': overall_level,
        'skill_scores': skill_scores,
        'weak_skills': weakest,
        'recommendation': f"Focus on {' and '.join(weakest)}.",
    }


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
    objectives = module.objectives or []
    objective_text = '; '.join(objectives) if objectives else module.description
    lesson = (
        f'{module.title}: {module.description} '
        f'Learning objectives: {objective_text}.'
    ).strip()
    practice_question = (
        f'Write one English sentence that demonstrates: '
        f'{objectives[0] if objectives else module.title}.'
    )
    return {
        'session_id': session.id,
        'lesson': lesson,
        'practice_question': practice_question,
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
    score, feedback = generate_teacher_feedback(answer)
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
