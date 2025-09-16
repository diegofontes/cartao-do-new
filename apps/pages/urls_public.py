from django.urls import path
from . import views

app_name = "pages_public"

urlpatterns = [
    path("politica_de_privacidade", views.privacy_public, name="privacy"),
    path("termos_de_uso", views.terms_public, name="terms"),
]

