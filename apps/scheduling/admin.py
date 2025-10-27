from django.contrib import admin

from .models import SchedulingService, ServiceAvailability, Appointment, RescheduleRequest


@admin.register(SchedulingService)
class SchedulingServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "card", "timezone", "duration_minutes", "is_active", "created_at")
    list_filter = ("is_active", "timezone", "card")
    search_fields = ("name", "card__title", "card__nickname")


@admin.register(ServiceAvailability)
class ServiceAvailabilityAdmin(admin.ModelAdmin):
    list_display = ("service", "rule_type", "weekday", "date", "start_time", "end_time")
    list_filter = ("rule_type", "service__card")
    search_fields = ("service__name", "service__card__title")


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("user_name", "service", "start_at_utc", "end_at_utc", "status", "public_code", "created_at")
    list_filter = ("status", "service__card", "service")
    search_fields = ("user_name", "user_email", "user_phone", "public_code")
    readonly_fields = ("created_at", "updated_at", "public_code", "token")
    ordering = ("-start_at_utc",)


@admin.register(RescheduleRequest)
class RescheduleRequestAdmin(admin.ModelAdmin):
    list_display = ("appointment", "status", "created_at", "requested_start_at_utc", "preferred_by", "approved_by")
    list_filter = ("status", "appointment__service__card")
    search_fields = ("appointment__user_name", "appointment__public_code")
    readonly_fields = ("created_at", "updated_at", "requested_ip", "action_ip")

    @admin.display(description="Solicitado por")
    def preferred_by(self, obj):
        return obj.requested_by or "customer"
