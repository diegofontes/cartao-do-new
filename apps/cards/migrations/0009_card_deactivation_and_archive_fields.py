from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0008_alter_avatar_and_gallery_max_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="card",
            name="deactivation_marked",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="card",
            name="deactivation_marked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="card",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="card",
            name="archived_reason",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="card",
            name="nickname_locked_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

