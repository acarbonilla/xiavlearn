from django.core.management.base import BaseCommand
from learning.models import Skill, CurriculumLevel, Module


class Command(BaseCommand):
    help = 'Seed initial learning data (skills, curriculum levels, modules)'

    def handle(self, *args, **options):
        skills = ['Grammar', 'Vocabulary', 'Speaking', 'Listening', 'Pronunciation']
        levels = [
            ('A1', 'Beginner'),
            ('A2', 'Elementary'),
            ('B1', 'Intermediate'),
            ('B2', 'Upper Intermediate'),
        ]

        for name in skills:
            Skill.objects.get_or_create(name=name)

        for code, name in levels:
            CurriculumLevel.objects.get_or_create(level_code=code, defaults={'name': name})

        # Sample modules mapping
        samples = [
            ('A1', 'Grammar', 'Simple Present Tense'),
            ('A2', 'Grammar', 'Past Tense'),
            ('A2', 'Vocabulary', 'Daily Conversation'),
            ('B1', 'Speaking', 'Workplace Conversation'),
            ('B2', 'Speaking', 'Presentation Practice'),
        ]

        for level_code, skill_name, title in samples:
            try:
                level = CurriculumLevel.objects.get(level_code=level_code)
                skill = Skill.objects.get(name=skill_name)
            except (CurriculumLevel.DoesNotExist, Skill.DoesNotExist):
                continue
            Module.objects.get_or_create(
                level=level,
                skill=skill,
                title=title,
                defaults={'description': '', 'objectives': []},
            )

        self.stdout.write(self.style.SUCCESS('Seeded learning data successfully.'))
