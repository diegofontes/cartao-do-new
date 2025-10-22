from django.contrib import admin
from .models import Card, CardAddress, LinkButton, GalleryItem, SocialLink


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "status", "published_at")
    list_filter = ("status",)
    search_fields = ("title", "owner__username")


@admin.register(CardAddress)
class CardAddressAdmin(admin.ModelAdmin):
    list_display = ("card", "label", "cep", "cidade", "uf")
    list_filter = ("uf",)


@admin.register(LinkButton)
class LinkButtonAdmin(admin.ModelAdmin):
    list_display = ("card", "label", "order")


@admin.register(GalleryItem)
class GalleryItemAdmin(admin.ModelAdmin):
    list_display = ("card", "caption", "importance", "visible_in_gallery", "service", "order")
    list_filter = ("visible_in_gallery", "service")
    search_fields = ("caption",)


@admin.register(SocialLink)
class SocialLinkAdmin(admin.ModelAdmin):
    list_display = ("card", "platform", "label", "url", "order", "is_active")
    list_filter = ("platform", "is_active")
