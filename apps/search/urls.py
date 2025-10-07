from django.urls import path

from . import views_public as views

app_name = "search_public"

urlpatterns = [
    path("", views.search_page, name="home"),
    path("results", views.search_results, name="results"),
    path("geocode", views.search_geocode, name="geocode"),
    path("ping", views.ping, name="ping"),
    path("geocode/cep", views.geocode_stub, name="geocode_stub"),
    path("cards", views.cards_api, name="cards_api"),
    path("cards/nearby", views.cards_nearby_partial, name="cards_nearby"),
    path("healthz", views.healthcheck, name="healthz"),
]
