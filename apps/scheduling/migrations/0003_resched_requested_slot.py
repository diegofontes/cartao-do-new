from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scheduling", "0002_public_code_and_reschedule"),
    ]

    operations = [
        migrations.AddField(
            model_name="reschedulerequest",
            name="requested_end_at_utc",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reschedulerequest",
            name="requested_start_at_utc",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
