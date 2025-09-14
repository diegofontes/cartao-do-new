from django.contrib import admin
from .models import MeteringEvent, PricingRule


@admin.register(PricingRule)
class PricingRuleAdmin(admin.ModelAdmin):
    list_display = ("code", "resource_type", "event_type", "unit_price_cents", "cadence", "is_active")
    list_filter = ("resource_type", "event_type", "cadence", "is_active")


@admin.register(MeteringEvent)
class MeteringEventAdmin(admin.ModelAdmin):
    list_display = ("user", "resource_type", "event_type", "quantity", "unit_price_cents", "occurred_at")
    list_filter = ("resource_type", "event_type")
    date_hierarchy = "occurred_at"

