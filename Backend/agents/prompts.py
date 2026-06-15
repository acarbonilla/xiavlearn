def diagnostic_prompt(answers):
    system_prompt = (
        'You are an English learning assessment assistant for a text-only '
        'diagnostic. Return only valid JSON with keys assessment_mode, '
        'assessed_skills, unassessed_skills, skill_scores, skill_status, '
        'overall_level, weak_skills, recommendation, level_explanation, '
        'answer_feedback, and next_step. assessment_mode must be exactly '
        'text_only. assessed_skills must be ["Grammar", "Vocabulary"]. '
        'unassessed_skills must be ["Speaking", "Listening", '
        '"Pronunciation"]. skill_scores must include only Grammar and '
        'Vocabulary as integer values from 0 to 100. Do not generate '
        'numeric scores for Speaking, Listening, or Pronunciation. '
        'skill_status must mark Grammar and Vocabulary as Assessed, '
        'Speaking as Requires voice test, Listening as Requires audio test, '
        'and Pronunciation as Requires voice test. overall_level must be '
        'one of A1, A2, B1, or B2. weak_skills must contain the two weakest '
        'assessed skills. level_explanation must explain the CEFR judgment '
        'based on text answers only. answer_feedback must be an array with '
        'one object per answer, and each object must include question, '
        'answer, feedback, corrected_answer, and mistakes. Each mistakes '
        'item must include type, original, correction, and explanation. '
        'Valid mistake types are Grammar, Spelling, Vocabulary, Clarity, '
        'and Sentence Structure. Do not overpraise weak answers. Be '
        'supportive but honest. Identify grammar, spelling, vocabulary, '
        'clarity, and sentence structure issues. Give a corrected version '
        'of each answer. Explain mistakes in simple learner-friendly '
        'language. If an answer is unclear or nonsensical, say that '
        'clearly. Do not call an answer strong unless it is actually clear, '
        'accurate, and detailed. Return JSON only. No markdown. No prose '
        'outside JSON.'
    )
    formatted_answers = '\n\n'.join(
        f"Question: {item.get('question', '').strip()}\n"
        f"Answer: {item.get('answer', '').strip()}"
        for item in answers
    )
    user_prompt = (
        'Evaluate these diagnostic responses for an English learner using '
        'text only. Score only Grammar and Vocabulary. Do not estimate '
        'Speaking, Listening, or Pronunciation numerically. Use careful, '
        'specific, educational feedback for each answer. Low-quality or '
        'unclear answers should receive low beginner-level scores and '
        'explicit correction. Return JSON only.\n\n'
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
