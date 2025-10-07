from django.urls import path

from . import views_dashboard as views

app_name = "search_dashboard"

urlpatterns = [
    path("cards/<uuid:card_id>/panel", views.profile_panel, name="profile_panel"),
    path("cards/<uuid:card_id>/save", views.profile_save, name="profile_save"),
    path("cards/<uuid:card_id>/deactivate", views.profile_deactivate, name="profile_deactivate"),
    path("cards/<uuid:card_id>/preview", views.profile_preview, name="profile_preview"),
    path("geocode", views.geocode_stub, name="geocode_stub"),
]
