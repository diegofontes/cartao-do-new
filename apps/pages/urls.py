from django.urls import path
from . import views

app_name = "pages"

urlpatterns = [
    path("politica_de_privacidade", views.privacy_app, name="privacy"),
    path("termos_de_uso", views.terms_app, name="terms"),
    path("page/home", views.home, name="home"),
]
