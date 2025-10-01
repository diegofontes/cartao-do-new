from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.index, name="index"),
    path("agenda/", views.agenda, name="agenda"),
    # Timeline (list) partial + quick actions
    path("agenda/list", views.agenda_list_partial, name="agenda_list_partial"),
    path("agenda/list/<uuid:id>/confirm", views.agenda_list_confirm, name="agenda_list_confirm"),
    path("agenda/list/<uuid:id>/reject", views.agenda_list_reject, name="agenda_list_reject"),
    path("agenda/list/<uuid:id>/cancel", views.agenda_list_cancel, name="agenda_list_cancel"),
    path("agenda/events", views.agenda_events, name="agenda_events"),
    path("agenda/events/<uuid:id>/sidebar", views.agenda_event_sidebar, name="agenda_event_sidebar"),
    path("agenda/events/<uuid:id>/approve", views.agenda_event_approve, name="agenda_event_approve"),
    path("agenda/events/<uuid:id>/deny", views.agenda_event_deny, name="agenda_event_deny"),
]
