# Day 2 — Curriculum Database Validation & Expansion

**Date:** 2026-06-12

**Status:** ✅ Complete

## Goal
Validate the Day 1 database foundation and expand the CEFR-based curriculum structure for the XiAv Learn MVP.

## Completed Database Checks

### 1. Project Validation
- ✅ `python manage.py check` — System check passed (no issues)
- ✅ `python manage.py makemigrations` — No new migrations detected (Day 1 migrations already applied)
- ✅ `python manage.py migrate` — All migrations applied successfully

### 2. Django Models Verified
All required Day 1 models exist in `Backend/learning/models.py`:
- ✅ LearnerProfile
- ✅ Skill
- ✅ SkillMastery
- ✅ CurriculumLevel
- ✅ Module
- ✅ StudySession
- ✅ StudyPlan

Each model has a clear `__str__` method for admin display.

### 3. Admin Registration Verified
All models are registered in `Backend/learning/admin.py` with:
- ✅ LearnerProfile — displays user, current_level, target_level, daily_study_minutes
- ✅ Skill — displays name, created_at
- ✅ SkillMastery — displays user, skill, level_code, score, status, last_updated
- ✅ CurriculumLevel — displays level_code, name, sort_order
- ✅ Module — displays title, level, skill, is_active, sort_order
- ✅ StudySession — displays user, session_type, module, started_at, completed_at
- ✅ StudyPlan — displays user, generated_at

## Seeded Data

### Skills (5 total)
1. Grammar
2. Vocabulary
3. Speaking
4. Listening
5. Pronunciation

### CEFR Curriculum Levels (4 total)
| Level Code | Name | Description | Sort Order |
|---|---|---|---|
| A1 | Beginner | Elementary proficiency - can understand and use familiar everyday expressions | 1 |
| A2 | Elementary | Elementary proficiency - can communicate in simple and routine tasks | 2 |
| B1 | Intermediate | Intermediate proficiency - can produce simple connected text on topics | 3 |
| B2 | Upper Intermediate | Upper intermediate proficiency - can interact with spontaneity and fluency | 4 |

### Modules (12 total)

#### A1 Level (3 modules)
1. **Grammar — Simple Present Tense**
   - Objectives:
     - Understand simple present tense
     - Use correct verb forms
     - Create basic daily routine sentences

2. **Vocabulary — Daily Objects**
   - Objectives:
     - Identify common daily objects
     - Use objects in simple sentences
     - Build basic noun vocabulary

3. **Speaking — Self Introduction**
   - Objectives:
     - Introduce yourself clearly
     - Say your name, location, and basic interests
     - Answer simple personal questions

#### A2 Level (3 modules)
4. **Grammar — Past Tense**
   - Objectives:
     - Understand regular past tense verbs
     - Use common irregular past tense verbs
     - Describe yesterday's activities

5. **Vocabulary — Daily Conversation**
   - Objectives:
     - Use common conversation phrases
     - Ask and answer everyday questions
     - Improve practical vocabulary

6. **Speaking — Asking and Answering Questions**
   - Objectives:
     - Ask basic information questions
     - Answer questions in complete sentences
     - Improve response confidence

#### B1 Level (3 modules)
7. **Grammar — Giving Opinions**
   - Objectives:
     - Express opinions clearly
     - Use because, however, and I think
     - Support ideas with simple reasons

8. **Vocabulary — Workplace Vocabulary**
   - Objectives:
     - Use common workplace terms
     - Understand professional expressions
     - Apply vocabulary in job-related situations

9. **Speaking — Workplace Conversation**
   - Objectives:
     - Handle basic workplace conversations
     - Explain tasks and problems
     - Respond politely in professional settings

#### B2 Level (3 modules)
10. **Grammar — Complex Sentences**
    - Objectives:
      - Use compound and complex sentences
      - Connect ideas with advanced conjunctions
      - Improve sentence variety

11. **Vocabulary — Professional Vocabulary**
    - Objectives:
      - Use advanced workplace vocabulary
      - Explain ideas with precise words
      - Improve formal communication

12. **Speaking — Presentation Practice**
    - Objectives:
      - Organize a short presentation
      - Speak with clear structure
      - Explain ideas confidently

## Database Verification Results

```
Skills: 5 ✅
Curriculum Levels: 4 ✅
Modules: 12 ✅
Module Objectives: All populated ✅
```

### Sample Module Verification
- **Simple Present Tense**: ['Understand simple present tense', 'Use correct verb forms', 'Create basic daily routine sentences']
- **Workplace Conversation**: ['Handle basic workplace conversations', 'Explain tasks and problems', 'Respond politely in professional settings']

## Notes for Diagnostic Agent

The Diagnostic Agent will use the curriculum structure to:

1. **Assess learner level** using the 4 CEFR levels (A1, A2, B1, B2)
2. **Identify skill gaps** across the 5 core skills (Grammar, Vocabulary, Speaking, Listening, Pronunciation)
3. **Recommend starting modules** based on initial assessment
4. **Track progress** via SkillMastery records
5. **Create personalized learning plans** via StudyPlan records

### Key Data Points:
- Each CurriculumLevel has a sort_order for proper progression
- Each Module has objectives that clarify learning outcomes
- Each Module links Level → Skill → Objectives (DAG structure)
- Modules can be filtered by level, skill, or status

## Notes for Curriculum Agent

The Curriculum Agent will use the seeded data to:

1. **Generate study paths** based on learner profile (current_level, target_level)
2. **Sequence modules** using sort_order within each level
3. **Select appropriate content** by matching skill masteries to available modules
4. **Adjust difficulty** by recommending A1 → A2 → B1 → B2 progression
5. **Create dynamic lesson plans** combining multiple modules into a StudyPlan

### Curriculum Strategy:
- Start learners at identified level (e.g., A1)
- Focus on weakest skills first (lowest SkillMastery.score)
- Sequence Grammar → Vocabulary → Speaking for each level
- Allow learners to set target_level (B1 or B2 recommended)
- Track progress via StudySession records

## Files Changed

- `Backend/learning/management/commands/seed_learning_data.py` — Expanded with 12 modules and objectives

## Commands Run

```bash
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py seed_learning_data
python manage.py shell -c "from learning.models import Skill, CurriculumLevel, Module; print(f'Skills: {Skill.objects.count()}'); print(f'Levels: {CurriculumLevel.objects.count()}'); print(f'Modules: {Module.objects.count()}')"
```

## Next Recommended Task

**Day 3 — Diagnostic Agent Workflow & API:**
- Create endpoints for learner assessment
- Implement SkillMastery evaluation logic
- Build Diagnostic Agent to classify learner level
- Create LearnerProfile via admin or API
- Test assessment workflow
