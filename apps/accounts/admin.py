from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _


User = get_user_model()


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # Show common columns + verification timestamp
    list_display = (
        "email",
        "username",
        "first_name",
        "last_name",
        "is_staff",
        "email_verified_at",
    )
    search_fields = ("email", "first_name", "last_name", "username")
    ordering = ("email",)
    readonly_fields = ("email_verified_at",)

    # Add our custom fields to the details page
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            _("Additional info"),
            {"fields": ("email_verified_at", "birth_date", "gender")},
        ),
    )

    # And to the add form as optional
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            _("Additional info"),
            {"classes": ("wide",), "fields": ("email", "first_name", "last_name", "birth_date", "gender")},
        ),
    )

