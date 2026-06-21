from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from agents.models import LessonSession, LessonTurn
from learning.models import CurriculumLevel, Module, Skill, SkillMastery, StudySession


class SkillMasteryAuditCommandTests(TestCase):
    def test_audit_command_flags_rows_that_match_teacher_practice_artifacts(self):
        user = User.objects.create_user(username='learner', password='test-password-123')
        level = CurriculumLevel.objects.create(
            level_code='A2',
            name='Elementary',
            sort_order=2,
        )
        grammar = Skill.objects.create(name='Grammar')
        vocabulary = Skill.objects.create(name='Vocabulary')
        module = Module.objects.create(
            level=level,
            skill=grammar,
            title='Past Tense',
            description='Practice regular and irregular past tense verbs.',
            objectives=['Describe yesterday activities'],
            sort_order=1,
        )

        study_session = StudySession.objects.create(
            user=user,
            module=module,
            session_type='guided_teacher_session',
            score=62,
        )
        lesson_session = LessonSession.objects.create(
            study_session=study_session,
            status='completed',
            current_turn=3,
            final_score=62,
        )
        turn = LessonTurn.objects.create(
            session=lesson_session,
            turn_number=1,
            teacher_task='Describe what you did yesterday.',
            student_answer='Yesterday, I go to school.',
            ai_feedback='Good attempt. Review verb tense.',
            correction='Yesterday, I went to school.',
            explanation='Use the past tense form.',
            encouragement='Keep practicing.',
            score=62,
        )
        suspicious_mastery = SkillMastery.objects.create(
            user=user,
            skill=grammar,
            level_code='A2',
            score=62,
            status='Learning',
        )
        SkillMastery.objects.filter(pk=suspicious_mastery.pk).update(
            last_updated=turn.created_at,
        )

        SkillMastery.objects.create(
            user=user,
            skill=vocabulary,
            level_code='A2',
            score=88,
            status='Mastered',
        )

        stdout = StringIO()
        call_command('audit_skillmastery_teacher_pollution', stdout=stdout)

        output = stdout.getvalue()
        self.assertIn('Found 1 suspicious SkillMastery rows.', output)
        self.assertIn(f'mastery_id={suspicious_mastery.id}', output)
        self.assertIn('user=learner', output)
        self.assertIn('skill=Grammar', output)
        self.assertIn('lesson_turn.score matched turn', output)
        self.assertNotIn('skill=Vocabulary', output)
