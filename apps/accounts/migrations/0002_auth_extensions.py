from django.db import migrations, models
import django.db.models.deletion
from django.db.models.functions import Lower
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="email_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                Lower("email"), name="accounts_user_email_lower_uniq"
            ),
        ),
        migrations.CreateModel(
            name="TrustedDevice",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False, editable=False, default=uuid.uuid4)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("device_id", models.CharField(max_length=64, db_index=True)),
                ("expires_at", models.DateTimeField()),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trusted_devices",
                        to="accounts.user",
                    ),
                ),
            ],
            options={},
        ),
        migrations.CreateModel(
            name="EmailChallenge",
            fields=[
                ("id", models.UUIDField(primary_key=True, serialize=False, editable=False, default=uuid.uuid4)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("purpose", models.CharField(max_length=20)),
                ("sent_to", models.EmailField(max_length=254)),
                ("code_hash", models.CharField(max_length=64)),
                ("attempts_left", models.PositiveSmallIntegerField(default=5)),
                ("expires_at", models.DateTimeField()),
                ("consumed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_challenges",
                        to="accounts.user",
                    ),
                ),
            ],
            options={},
        ),
    ]
