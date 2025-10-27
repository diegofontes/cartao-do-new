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
    path("agenda/reschedule", views.reschedule_index, name="reschedule_index"),
    path("agenda/reschedule/list", views.reschedule_list, name="reschedule_list"),
    path("agenda/reschedule/<uuid:id>/detail", views.reschedule_detail, name="reschedule_detail"),
    path("agenda/reschedule/<uuid:id>/slots", views.reschedule_slots, name="reschedule_slots"),
    path("agenda/reschedule/<uuid:id>/approve", views.reschedule_approve, name="reschedule_approve"),
    path("agenda/reschedule/<uuid:id>/reject", views.reschedule_reject, name="reschedule_reject"),
]
