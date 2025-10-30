from django.urls import path

from . import views

app_name = "jornal"

urlpatterns = [
    path("jornal/news", views.news_card, name="news"),
    path("jornal/helpers", views.helper_list, name="helper_list"),
    path("jornal/helpers/<slug:slug>", views.helper_detail, name="helper_detail"),
]

