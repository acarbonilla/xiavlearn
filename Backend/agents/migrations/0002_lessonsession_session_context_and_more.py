from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='lessonsession',
            name='session_context',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='lessonsession',
            name='session_mode',
            field=models.CharField(
                choices=[
                    ('text', 'Text'),
                    ('speaking', 'Speaking'),
                    ('listening', 'Listening'),
                    ('pronunciation', 'Pronunciation'),
                ],
                default='text',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='lessonturn',
            name='evaluation_breakdown',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='lessonturn',
            name='target_focus',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='lessonturn',
            name='task_type',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
    ]
