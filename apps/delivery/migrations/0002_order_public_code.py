from django.db import migrations, models
from django.db.models import Q
import string
import secrets


def _generate_code(existing: set[str]) -> str:
    alphabet = string.ascii_uppercase + string.digits
    for _ in range(15):
        code = "D" + "".join(secrets.choice(alphabet) for _ in range(7))
        if code not in existing:
            existing.add(code)
            return code
    raise RuntimeError("unable to generate unique order public_code")


def populate_public_code(apps, schema_editor):
    Order = apps.get_model("delivery", "Order")
    existing = set(
        Order.objects.exclude(public_code__isnull=True).exclude(public_code="").values_list("public_code", flat=True)
    )
    for order in Order.objects.filter(Q(public_code__isnull=True) | Q(public_code="")):
        code = _generate_code(existing)
        order.public_code = code
        order.save(update_fields=["public_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("delivery", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="public_code",
            field=models.CharField(blank=True, max_length=12, null=True),
        ),
        migrations.RunPython(populate_public_code, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="order",
            name="public_code",
            field=models.CharField(max_length=12, unique=True),
        ),
    ]
