from django.contrib import admin
from .models import CustomerProfile, UsageEvent, Invoice, InvoiceLine

@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "stripe_customer_id", "default_payment_method", "is_active")

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
