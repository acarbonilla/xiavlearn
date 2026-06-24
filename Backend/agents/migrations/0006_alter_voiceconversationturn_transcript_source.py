from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0005_voiceconversationsession_voiceconversationturn'),
    ]

    operations = [
        migrations.AlterField(
            model_name='voiceconversationturn',
            name='transcript_source',
            field=models.CharField(
                choices=[
                    ('manual', 'Manual'),
                    ('deepgram', 'Deepgram'),
                    ('deepgram_streaming', 'Deepgram Streaming'),
                    ('fallback', 'Fallback'),
                ],
                default='manual',
                max_length=50,
            ),
        ),
    ]
