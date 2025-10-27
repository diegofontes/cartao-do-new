from django.db import migrations, models
from django.conf import settings
from django.db.models import Q
import secrets
import string
import uuid


def _generate_code(existing: set[str]) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(15):
        code = "A" + "".join(secrets.choice(alphabet) for _ in range(7))
        if code not in existing:
            existing.add(code)
            return code
    raise RuntimeError("unable to generate unique appointment public_code")


def populate_public_code(apps, schema_editor):
    Appointment = apps.get_model("scheduling", "Appointment")
    existing = set(
        Appointment.objects.exclude(public_code__isnull=True).exclude(public_code="").values_list("public_code", flat=True)
    )
    for ap in Appointment.objects.filter(Q(public_code__isnull=True) | Q(public_code="")):
        code = _generate_code(existing)
        ap.public_code = code
        ap.save(update_fields=["public_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("scheduling", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="public_code",
            field=models.CharField(blank=True, max_length=12, null=True),
        ),
        migrations.RunPython(populate_public_code, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="appointment",
            name="public_code",
            field=models.CharField(max_length=12, unique=True),
        ),
        migrations.CreateModel(
            name="RescheduleRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(max_length=20, choices=[("requested", "Requested"), ("approved", "Approved"), ("rejected", "Rejected"), ("expired", "Expired")], default="requested")),
                ("requested_by", models.CharField(max_length=20, default="customer")),
                ("preferred_windows", models.JSONField(default=list, blank=True)),
                ("reason", models.TextField(blank=True)),
                ("owner_message", models.TextField(blank=True)),
                ("new_start_at_utc", models.DateTimeField(blank=True, null=True)),
                ("new_end_at_utc", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("requested_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("action_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("appointment", models.ForeignKey(on_delete=models.CASCADE, related_name="reschedule_requests", to="scheduling.appointment")),
                ("approved_by", models.ForeignKey(on_delete=models.SET_NULL, blank=True, null=True, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "abstract": False,
            },
        ),
        migrations.AddIndex(
            model_name="reschedulerequest",
            index=models.Index(fields=["appointment", "status", "created_at"], name="scheduling_reschedule_idx"),
        ),
    ]
