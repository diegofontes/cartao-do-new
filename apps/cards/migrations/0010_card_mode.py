from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0009_card_deactivation_and_archive_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="card",
            name="mode",
            field=models.CharField(
                choices=[("appointment", "Appointment"), ("delivery", "Delivery")],
                default="appointment",
                max_length=20,
            ),
        ),
    ]

