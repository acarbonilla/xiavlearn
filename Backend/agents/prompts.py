def diagnostic_prompt(answers):
    system_prompt = (
        'You are an English learning assessment assistant. Return only valid '
        'JSON with keys overall_level, skill_scores, weak_skills, '
        'recommendation, level_explanation, answer_feedback, and next_step. '
        'skill_scores must include Grammar, Vocabulary, Speaking, Listening, '
        'and Pronunciation as integer values from 0 to 100. overall_level '
        'must be one of A1, A2, B1, or B2. weak_skills must be the two '
        'weakest skill names. level_explanation must explain why that level '
        'was assigned. answer_feedback must be an array with one object per '
        'answer, and each object must include question, answer, and feedback. '
        'next_step must be one short action-oriented sentence.'
    )
    formatted_answers = '\n\n'.join(
        f"Question: {item.get('question', '').strip()}\n"
        f"Answer: {item.get('answer', '').strip()}"
        for item in answers
    )
    user_prompt = (
        'Evaluate these diagnostic responses for an English learner. '
        'Be concise, deterministic, supportive, and aligned to CEFR-style '
        'beginner-to-intermediate feedback. Return JSON only.\n\n'
        f'{formatted_answers}'
    )
    return system_prompt, user_prompt


def teacher_lesson_prompt(module):
    system_prompt = (
        'You are an English tutor. Return only valid JSON with keys '
        'lesson and practice_question. Keep the lesson short, clear, and '
        'appropriate for the supplied module and level.'
    )
    objectives = module.objectives or []
    objective_text = '; '.join(objectives) if objectives else module.description
    user_prompt = (
        f'Title: {module.title}\n'
        f'Level: {module.level.level_code}\n'
        f'Skill: {module.skill.name}\n'
        f'Description: {module.description}\n'
        f'Objectives: {objective_text}'
    )
    return system_prompt, user_prompt


def teacher_feedback_prompt(module, answer):
    system_prompt = (
        'You are an English tutor reviewing one learner response. Return '
        'only valid JSON with keys score and feedback. score must be an '
        'integer from 0 to 100. feedback must be concise, supportive, and '
        'specific to the answer.'
    )
    objectives = module.objectives or []
    objective_text = '; '.join(objectives) if objectives else module.description
    user_prompt = (
        f'Module title: {module.title}\n'
        f'Level: {module.level.level_code}\n'
        f'Skill: {module.skill.name}\n'
        f'Objectives: {objective_text}\n'
        f'Learner answer: {answer.strip()}'
    )
    return system_prompt, user_prompt


def coach_summary_prompt(profile_level, weakest_skill, recent_session_count):
    system_prompt = (
        'You are a concise learning coach. Return only valid JSON with '
        'keys summary and next_step. Keep both short, practical, and '
        'motivating without exaggeration.'
    )
    weakest_skill_name = weakest_skill.skill.name if weakest_skill else 'None'
    user_prompt = (
        f'Current learner level: {profile_level or "Unknown"}\n'
        f'Weakest skill: {weakest_skill_name}\n'
        f'Completed recent sessions: {recent_session_count}'
    )
    return system_prompt, user_prompt
