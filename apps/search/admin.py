from django.contrib import admin

from .models import SearchProfile


@admin.register(SearchProfile)
class SearchProfileAdmin(admin.ModelAdmin):
    list_display = ("card", "category", "active", "radius_km", "created_at")
    search_fields = ("card__title", "card__nickname")
    list_filter = ("category", "active")
