import uuid
import django.db.models.deletion
from django.db import migrations, models, transaction


def seed_status_changes(apps, schema_editor):
    Order = apps.get_model("delivery", "Order")
    OrderStatusChange = apps.get_model("delivery", "OrderStatusChange")

    with transaction.atomic():
        for order in Order.objects.all().iterator():
            pending = OrderStatusChange.objects.create(
                order=order,
                status="pending",
                source="migration_seed",
            )
            OrderStatusChange.objects.filter(pk=pending.pk).update(
                created_at=order.created_at,
                updated_at=order.created_at,
            )
            if order.status != "pending":
                final = OrderStatusChange.objects.create(
                    order=order,
                    status=order.status,
                    source="migration_seed",
                )
                OrderStatusChange.objects.filter(pk=final.pk).update(
                    created_at=order.updated_at,
                    updated_at=order.updated_at,
                )


class Migration(migrations.Migration):

    dependencies = [
        ("delivery", "0002_order_public_code"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderStatusChange",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("accepted", "Accepted"), ("rejected", "Rejected"), ("preparing", "Preparing"), ("ready", "Ready"), ("shipped", "Shipped"), ("completed", "Completed"), ("cancelled", "Cancelled")], max_length=20)),
                ("source", models.CharField(blank=True, max_length=32)),
                ("note", models.CharField(blank=True, max_length=200)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="status_changes", to="delivery.order")),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="orderstatuschange",
            index=models.Index(fields=["order", "created_at"], name="delivery_ord_idx"),
        ),
        migrations.RunPython(seed_status_changes, migrations.RunPython.noop),
    ]
