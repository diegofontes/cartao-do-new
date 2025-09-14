from django.urls import path
from . import views

app_name = "scheduling"

urlpatterns = [
    path("services/<uuid:id>/slots", views.list_slots, name="slots"),
    path("services/<uuid:id>/appointments", views.create_appointment, name="appointments_create"),
    # HTMX for scheduling services attached to a card
    path("cards/<uuid:card_id>/services", views.services_partial, name="services_partial"),
    path("cards/<uuid:card_id>/services/new", views.service_form, name="service_form_new"),
    path("cards/<uuid:card_id>/services/create", views.service_save, name="service_create"),
    path("cards/<uuid:card_id>/services/<uuid:id>/edit", views.service_form, name="service_form_edit"),
    path("cards/<uuid:card_id>/services/<uuid:id>/save", views.service_save, name="service_save"),
    path("cards/<uuid:card_id>/services/<uuid:id>/delete", views.service_delete, name="service_delete"),
    # Availability CRUD
    path("cards/<uuid:card_id>/services/<uuid:service_id>/availability", views.availability_partial, name="availability_partial"),
    path("cards/<uuid:card_id>/services/<uuid:service_id>/availability/new", views.availability_form, name="availability_form_new"),
    path("cards/<uuid:card_id>/services/<uuid:service_id>/availability/create", views.availability_save, name="availability_create"),
    path("cards/<uuid:card_id>/services/<uuid:service_id>/availability/<uuid:id>/edit", views.availability_form, name="availability_form_edit"),
    path("cards/<uuid:card_id>/services/<uuid:service_id>/availability/<uuid:id>/save", views.availability_save, name="availability_save"),
    path("cards/<uuid:card_id>/services/<uuid:service_id>/availability/<uuid:id>/delete", views.availability_delete, name="availability_delete"),
]
