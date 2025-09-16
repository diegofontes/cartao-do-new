from django.urls import path
from . import views

app_name = "cards"

urlpatterns = [
    path("", views.list_cards, name="list"),
    path("new/", views.create_card, name="create"),
    path("<uuid:id>/", views.card_detail, name="detail"),
    path("<uuid:id>/edit/", views.edit_card, name="edit"),
    path("<uuid:id>/publish", views.publish_card, name="publish"),
    path("<uuid:id>/publish-modal", views.publish_modal, name="publish_modal"),
    path("nicknames/check", views.check_nickname, name="check_nickname"),
    path("<uuid:id>/avatar", views.upload_avatar, name="upload_avatar"),
    path("<uuid:id>/delete", views.delete_card, name="delete"),
    # HTMX partials
    path("<uuid:id>/links", views.links_partial, name="links_partial"),
    path("<uuid:id>/links/add", views.add_link, name="add_link"),
    path("links/<uuid:link_id>/delete", views.delete_link, name="delete_link"),
    path("<uuid:id>/addresses", views.addresses_partial, name="addresses_partial"),
    path("<uuid:id>/addresses/new", views.address_form, name="address_form"),
    path("<uuid:id>/addresses/add", views.add_address, name="add_address"),
    path("addresses/<uuid:address_id>/delete", views.delete_address, name="delete_address"),
    path("<uuid:id>/gallery", views.gallery_partial, name="gallery_partial"),
    path("<uuid:id>/gallery/add", views.add_gallery_item, name="add_gallery_item"),
    path("gallery/<uuid:item_id>/delete", views.delete_gallery_item, name="delete_gallery_item"),
    # CEP lookup (global)
    path("cep/lookup", views.cep_lookup, name="cep_lookup"),
    # Social links
    path("<uuid:id>/social-links", views.social_links_partial, name="social_links_partial"),
    path("<uuid:id>/social-links/add", views.add_social_link, name="add_social_link"),
    path("social-links/<uuid:link_id>/delete", views.delete_social_link, name="delete_social_link"),
    # Tabs config
    path("<uuid:id>/tabs", views.tabs_partial, name="tabs_partial"),
    path("<uuid:id>/tabs/save", views.set_tabs_order, name="set_tabs_order"),
]
