from datetime import timedelta

from django.core.management.base import BaseCommand

from agents.models import LessonSession
from learning.models import SkillMastery


def _within_window(left, right, window):
    if left is None or right is None:
        return False
    return abs(left - right) <= window


class Command(BaseCommand):
    help = (
        'Identify SkillMastery rows whose score and timestamp line up with '
        'teacher-practice session artifacts.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--window-minutes',
            type=int,
            default=10,
            help='Maximum timestamp delta to treat as suspicious. Default: 10.',
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Optional username filter for a narrower audit.',
        )

    def handle(self, *args, **options):
        window = timedelta(minutes=options['window_minutes'])
        mastery_qs = SkillMastery.objects.select_related('user', 'skill')
        if options.get('username'):
            mastery_qs = mastery_qs.filter(user__username=options['username'])

        lesson_sessions = (
            LessonSession.objects.select_related(
                'study_session__user',
                'study_session__module__skill',
            )
            .prefetch_related('turns')
            .filter(study_session__module__isnull=False)
        )

        practice_index = {}
        for lesson_session in lesson_sessions:
            module = lesson_session.study_session.module
            if module is None:
                continue
            key = (lesson_session.study_session.user_id, module.skill_id)
            practice_index.setdefault(key, []).append(lesson_session)

        suspicious_rows = []
        for mastery in mastery_qs.order_by('user__username', 'skill__name'):
            matches = []
            for lesson_session in practice_index.get((mastery.user_id, mastery.skill_id), []):
                study_session = lesson_session.study_session
                completed_at = lesson_session.completed_at or study_session.completed_at

                if (
                    lesson_session.final_score is not None
                    and lesson_session.final_score == mastery.score
                    and _within_window(mastery.last_updated, completed_at, window)
                ):
                    matches.append(
                        f'lesson_session.final_score matched session {lesson_session.id}'
                    )

                if (
                    study_session.score is not None
                    and study_session.score == mastery.score
                    and _within_window(
                        mastery.last_updated,
                        study_session.completed_at or study_session.started_at,
                        window,
                    )
                ):
                    matches.append(
                        f'study_session.score matched session {study_session.id}'
                    )

                for turn in lesson_session.turns.all():
                    if (
                        turn.score is not None
                        and turn.score == mastery.score
                        and _within_window(mastery.last_updated, turn.created_at, window)
                    ):
                        matches.append(
                            f'lesson_turn.score matched turn {turn.id} in session {lesson_session.id}'
                        )

            if matches:
                suspicious_rows.append((mastery, sorted(set(matches))))

        if not suspicious_rows:
            self.stdout.write(
                self.style.SUCCESS('No suspicious SkillMastery rows found.')
            )
            return

        self.stdout.write(
            self.style.WARNING(
                f'Found {len(suspicious_rows)} suspicious SkillMastery rows.'
            )
        )
        for mastery, matches in suspicious_rows:
            self.stdout.write(
                (
                    f'mastery_id={mastery.id} '
                    f'user={mastery.user.username} '
                    f'skill={mastery.skill.name} '
                    f'score={mastery.score} '
                    f'level={mastery.level_code} '
                    f'last_updated={mastery.last_updated.isoformat()} '
                    f'reasons={"; ".join(matches)}'
                )
            )
