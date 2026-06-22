from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0002_lessonsession_session_context_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='lessonturn',
            name='target_text',
            field=models.TextField(blank=True),
        ),
    ]
