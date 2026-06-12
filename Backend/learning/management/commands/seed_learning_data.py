from django.core.management.base import BaseCommand
from learning.models import Skill, CurriculumLevel, Module


class Command(BaseCommand):
    help = 'Seed initial learning data (skills, curriculum levels, modules)'

    def handle(self, *args, **options):
        # Seed skills
        skills = ['Grammar', 'Vocabulary', 'Speaking', 'Listening', 'Pronunciation']
        for name in skills:
            Skill.objects.get_or_create(name=name)

        # Seed curriculum levels with descriptions and sort order
        levels = [
            {
                'level_code': 'A1',
                'name': 'Beginner',
                'description': 'Elementary proficiency - can understand and use familiar everyday expressions',
                'sort_order': 1,
            },
            {
                'level_code': 'A2',
                'name': 'Elementary',
                'description': 'Elementary proficiency - can communicate in simple and routine tasks',
                'sort_order': 2,
            },
            {
                'level_code': 'B1',
                'name': 'Intermediate',
                'description': 'Intermediate proficiency - can produce simple connected text on topics',
                'sort_order': 3,
            },
            {
                'level_code': 'B2',
                'name': 'Upper Intermediate',
                'description': 'Upper intermediate proficiency - can interact with spontaneity and fluency',
                'sort_order': 4,
            },
        ]
        for level_data in levels:
            CurriculumLevel.objects.update_or_create(
                level_code=level_data['level_code'],
                defaults={
                    'name': level_data['name'],
                    'description': level_data['description'],
                    'sort_order': level_data['sort_order'],
                },
            )

        # Seed modules with objectives
        modules_data = [
            {
                'level_code': 'A1',
                'skill_name': 'Grammar',
                'title': 'Simple Present Tense',
                'description': 'Learn to use simple present tense for daily activities and habits',
                'objectives': [
                    'Understand simple present tense',
                    'Use correct verb forms',
                    'Create basic daily routine sentences',
                ],
                'sort_order': 1,
            },
            {
                'level_code': 'A1',
                'skill_name': 'Vocabulary',
                'title': 'Daily Objects',
                'description': 'Identify and use vocabulary for common daily objects',
                'objectives': [
                    'Identify common daily objects',
                    'Use objects in simple sentences',
                    'Build basic noun vocabulary',
                ],
                'sort_order': 2,
            },
            {
                'level_code': 'A1',
                'skill_name': 'Speaking',
                'title': 'Self Introduction',
                'description': 'Practice introducing yourself with basic information',
                'objectives': [
                    'Introduce yourself clearly',
                    'Say your name, location, and basic interests',
                    'Answer simple personal questions',
                ],
                'sort_order': 3,
            },
            {
                'level_code': 'A2',
                'skill_name': 'Grammar',
                'title': 'Past Tense',
                'description': 'Master regular and common irregular past tense verbs',
                'objectives': [
                    'Understand regular past tense verbs',
                    'Use common irregular past tense verbs',
                    'Describe yesterday\'s activities',
                ],
                'sort_order': 1,
            },
            {
                'level_code': 'A2',
                'skill_name': 'Vocabulary',
                'title': 'Daily Conversation',
                'description': 'Learn practical vocabulary for everyday conversations',
                'objectives': [
                    'Use common conversation phrases',
                    'Ask and answer everyday questions',
                    'Improve practical vocabulary',
                ],
                'sort_order': 2,
            },
            {
                'level_code': 'A2',
                'skill_name': 'Speaking',
                'title': 'Asking and Answering Questions',
                'description': 'Develop skills for basic information exchange',
                'objectives': [
                    'Ask basic information questions',
                    'Answer questions in complete sentences',
                    'Improve response confidence',
                ],
                'sort_order': 3,
            },
            {
                'level_code': 'B1',
                'skill_name': 'Grammar',
                'title': 'Giving Opinions',
                'description': 'Express opinions and support ideas with reasons',
                'objectives': [
                    'Express opinions clearly',
                    'Use because, however, and I think',
                    'Support ideas with simple reasons',
                ],
                'sort_order': 1,
            },
            {
                'level_code': 'B1',
                'skill_name': 'Vocabulary',
                'title': 'Workplace Vocabulary',
                'description': 'Learn workplace-related vocabulary and expressions',
                'objectives': [
                    'Use common workplace terms',
                    'Understand professional expressions',
                    'Apply vocabulary in job-related situations',
                ],
                'sort_order': 2,
            },
            {
                'level_code': 'B1',
                'skill_name': 'Speaking',
                'title': 'Workplace Conversation',
                'description': 'Communicate effectively in workplace settings',
                'objectives': [
                    'Handle basic workplace conversations',
                    'Explain tasks and problems',
                    'Respond politely in professional settings',
                ],
                'sort_order': 3,
            },
            {
                'level_code': 'B2',
                'skill_name': 'Grammar',
                'title': 'Complex Sentences',
                'description': 'Use advanced sentence structures with multiple clauses',
                'objectives': [
                    'Use compound and complex sentences',
                    'Connect ideas with advanced conjunctions',
                    'Improve sentence variety',
                ],
                'sort_order': 1,
            },
            {
                'level_code': 'B2',
                'skill_name': 'Vocabulary',
                'title': 'Professional Vocabulary',
                'description': 'Master advanced vocabulary for professional contexts',
                'objectives': [
                    'Use advanced workplace vocabulary',
                    'Explain ideas with precise words',
                    'Improve formal communication',
                ],
                'sort_order': 2,
            },
            {
                'level_code': 'B2',
                'skill_name': 'Speaking',
                'title': 'Presentation Practice',
                'description': 'Develop presentation skills for formal speaking',
                'objectives': [
                    'Organize a short presentation',
                    'Speak with clear structure',
                    'Explain ideas confidently',
                ],
                'sort_order': 3,
            },
        ]

        for module_data in modules_data:
            try:
                level = CurriculumLevel.objects.get(level_code=module_data['level_code'])
                skill = Skill.objects.get(name=module_data['skill_name'])
            except (CurriculumLevel.DoesNotExist, Skill.DoesNotExist):
                continue

            Module.objects.update_or_create(
                level=level,
                skill=skill,
                title=module_data['title'],
                defaults={
                    'description': module_data['description'],
                    'objectives': module_data['objectives'],
                    'sort_order': module_data['sort_order'],
                    'is_active': True,
                },
            )

        self.stdout.write(self.style.SUCCESS('Seeded learning data successfully.'))
