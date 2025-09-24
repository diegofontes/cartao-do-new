from django.db import migrations
from django.utils import timezone


def add_delivery_rule(apps, schema_editor):
    PricingRule = apps.get_model('metering', 'PricingRule')
    # Create a default pricing rule for delivery order accepted if it does not exist
    code = 'delivery_order_accepted'
    exists = PricingRule.objects.filter(code=code).exists()
    if not exists:
        PricingRule.objects.create(
            code=code,
            resource_type='delivery',
            event_type='order_accepted',
            unit_price_cents=100,  # default BRL 1,00 (adjust in admin as needed)
            cadence='per_event',
            is_active=True,
            starts_at=timezone.now(),
        )


def remove_delivery_rule(apps, schema_editor):
    PricingRule = apps.get_model('metering', 'PricingRule')
    PricingRule.objects.filter(code='delivery_order_accepted').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('metering', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_delivery_rule, remove_delivery_rule),
    ]

