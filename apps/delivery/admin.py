from django.contrib import admin
from .models import (
    MenuGroup,
    MenuItem,
    ModifierGroup,
    ModifierOption,
    Order,
    OrderItem,
    OrderItemOption,
    OrderItemText,
)


@admin.register(MenuGroup)
class MenuGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "card", "order", "is_active", "slug", "created_at")
    list_filter = ("is_active", "card")
    search_fields = ("name", "slug", "card__title", "card__nickname")
    ordering = ("card", "order", "created_at")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "card",
        "group",
        "base_price_cents",
        "is_active",
        "sku",
        "created_at",
    )
    list_filter = ("is_active", "group", "card")
    search_fields = ("name", "slug", "description", "sku", "card__title", "card__nickname")
    ordering = ("group", "-created_at")
    list_select_related = ("card", "group")
    prepopulated_fields = {"slug": ("name",)}


class ModifierOptionInline(admin.TabularInline):
    model = ModifierOption
    extra = 0
    ordering = ("order",)


@admin.register(ModifierGroup)
class ModifierGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "item", "type", "required", "min_choices", "max_choices", "order")
    list_filter = ("type", "required")
    search_fields = ("name", "item__name", "item__group__name", "item__card__title")
    ordering = ("item", "order")
    inlines = [ModifierOptionInline]
    list_select_related = ("item", "item__group", "item__card")


class OrderItemOptionInline(admin.TabularInline):
    model = OrderItemOption
    extra = 0


class OrderItemTextInline(admin.TabularInline):
    model = OrderItemText
    extra = 0


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("menu_item", "qty", "base_price_cents_snapshot", "line_subtotal_cents", "notes")
    readonly_fields = ()
    show_change_link = True


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "card",
        "status",
        "customer_name",
        "customer_phone",
        "fulfillment",
        "total_cents",
        "created_at",
    )
    list_filter = ("status", "fulfillment", "card")
    search_fields = ("code", "customer_name", "customer_phone", "customer_email", "card__nickname")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = [OrderItemInline]
    list_select_related = ("card",)


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "menu_item", "qty", "base_price_cents_snapshot", "line_subtotal_cents")
    search_fields = ("order__code", "menu_item__name")
    list_select_related = ("order", "menu_item")
    inlines = [OrderItemOptionInline, OrderItemTextInline]


@admin.register(ModifierOption)
class ModifierOptionAdmin(admin.ModelAdmin):
    list_display = ("label", "modifier_group", "price_delta_cents", "is_active", "order")
    list_filter = ("is_active",)
    search_fields = ("label", "modifier_group__name", "modifier_group__item__name")
    ordering = ("modifier_group", "order")


@admin.register(OrderItemOption)
class OrderItemOptionAdmin(admin.ModelAdmin):
    list_display = ("order_item", "modifier_option", "price_delta_cents_snapshot")
    list_select_related = ("order_item", "modifier_option")


@admin.register(OrderItemText)
class OrderItemTextAdmin(admin.ModelAdmin):
    list_display = ("order_item", "modifier_group", "text_value")
    list_select_related = ("order_item", "modifier_group")

