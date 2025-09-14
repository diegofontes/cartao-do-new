from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    path("payment-method/", views.payment_method, name="payment_method"),
    path("create-setup-intent/", views.create_setup_intent_view, name="create_setup_intent"),
    path("attach-payment-method/", views.attach_payment_method_view, name="attach_payment_method"),
    path("cancel/", views.cancel_view, name="cancel"),
    path("simulate-usage/", views.simulate_usage, name="simulate_usage"),
]
