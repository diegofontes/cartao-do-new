from django.urls import path
from . import views

app_name = "viewer"

urlpatterns = [
    path("order/<str:code>", views.order_detail, name="order_detail"),
    path("order/<str:code>/verify-last4", views.verify_last4, name="order_verify"),
    path("order/<str:code>/cancel", views.order_cancel, name="order_cancel"),
    path("order/<str:code>/reschedule-request", views.order_reschedule_request, name="order_reschedule_request"),
    path("order/<str:code>/status", views.order_status_partial, name="order_status_partial"),
    path("order/<str:code>/slots", views.order_reschedule_slots, name="order_reschedule_slots"),
]
