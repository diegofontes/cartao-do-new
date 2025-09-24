from django.urls import path
from . import views_admin as admin_views

app_name = "delivery"

urlpatterns = [
    # Admin (dashboard) endpoints for a card
    path("cards/<uuid:card_id>/menu", admin_views.menu_partial, name="menu_partial"),
    path("cards/<uuid:card_id>/menu/groups/add", admin_views.add_group, name="add_group"),
    path("cards/<uuid:card_id>/menu/items/add", admin_views.add_item, name="add_item"),
    path("items/<uuid:item_id>/delete", admin_views.delete_item, name="delete_item"),
    path("cards/<uuid:card_id>/menu/modifiers/add", admin_views.add_modifier_group, name="add_modifier_group"),
    path("cards/<uuid:card_id>/menu/options/add", admin_views.add_modifier_option, name="add_modifier_option"),
    # Delete endpoints
    path("groups/<uuid:group_id>/delete", admin_views.delete_group, name="delete_group"),
    path("modifiers/<uuid:modifier_group_id>/delete", admin_views.delete_modifier_group, name="delete_modifier_group"),
    path("options/<uuid:option_id>/delete", admin_views.delete_modifier_option, name="delete_modifier_option"),
    # Orders management (basic)
    path("cards/<uuid:card_id>/orders", admin_views.orders_partial, name="orders_partial"),
    path("orders/<uuid:order_id>/status", admin_views.update_order_status, name="update_order_status"),
    path("cards/<uuid:card_id>/orders/page", admin_views.orders_page, name="orders_page"),
]
