from django.contrib import admin
from django.utils.html import format_html

from . import models


@admin.register(models.NewsPost)
class NewsPostAdmin(admin.ModelAdmin):
    list_display = ("title", "is_public", "starts_at", "ends_at", "order", "updated_at")
    list_filter = (
        "is_public",
        ("starts_at", admin.DateFieldListFilter),
        ("ends_at", admin.DateFieldListFilter),
    )
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("preview_html", "body_html", "created_at", "updated_at")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "title",
                    "slug",
                    "is_public",
                    "order",
                    "starts_at",
                    "ends_at",
                    "body_markdown",
                    "preview_html",
                )
            },
        ),
        ("Cache", {"fields": ("body_html",), "classes": ("collapse",)}),
        ("Auditoria", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def preview_html(self, obj: models.NewsPost) -> str:
        if not obj.body_html:
            return format_html("<em>Sem conteúdo</em>")
        return format_html('<div class="preview-html">{}</div>', obj.body_html)

    preview_html.short_description = "Pré-visualização"


class HelperRuleInline(admin.TabularInline):
    model = models.HelperRule
    extra = 1
    fields = ("route_pattern", "is_active")


@admin.register(models.Helper)
class HelperAdmin(admin.ModelAdmin):
    list_display = ("title", "is_public", "order", "updated_at")
    list_filter = ("is_public",)
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("preview_html", "body_html", "created_at", "updated_at")
    inlines = [HelperRuleInline]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "title",
                    "slug",
                    "is_public",
                    "order",
                    "body_markdown",
                    "preview_html",
                )
            },
        ),
        ("Cache", {"fields": ("body_html",), "classes": ("collapse",)}),
        ("Auditoria", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def preview_html(self, obj: models.Helper) -> str:
        if not obj.body_html:
            return format_html("<em>Sem conteúdo</em>")
        return format_html('<div class="preview-html">{}</div>', obj.body_html)

    preview_html.short_description = "Pré-visualização"


@admin.register(models.HelperRule)
class HelperRuleAdmin(admin.ModelAdmin):
    list_display = ("route_pattern", "helper", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("route_pattern", "helper__title", "helper__slug")
    autocomplete_fields = ("helper",)
