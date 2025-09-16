from django.contrib import admin
from .models import CustomerProfile, UsageEvent, Invoice, InvoiceLine
from .utils import next_period_end

@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "stripe_customer_id",
        "default_payment_method",
        "is_active",
        "billing_anchor_day",
        "timezone",
        "next_charge_display",
    )

    def next_charge_display(self, obj: CustomerProfile):
        if obj.billing_anchor_day:
            try:
                return next_period_end(obj.timezone or "America/Sao_Paulo", obj.billing_anchor_day, obj.last_billed_period_end or None)
            except Exception:
                return "-"
        return "-"
    next_charge_display.short_description = "Próxima cobrança"

@admin.register(UsageEvent)
class UsageEventAdmin(admin.ModelAdmin):
    list_display = ("user", "units", "created_at")
    list_filter = ("user",)

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("user", "stripe_invoice_id", "amount_cents", "status", "period_start", "period_end")
    list_filter = ("status", "user")


@admin.register(InvoiceLine)
class InvoiceLineAdmin(admin.ModelAdmin):
    list_display = ("invoice", "metering_event", "amount_cents", "created_at")
    list_filter = ("invoice",)
