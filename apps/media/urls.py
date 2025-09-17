from django.urls import path
from . import views

app_name = "media"

urlpatterns = [
    path("p/<path:path>", views.image_public, name="image_public"),
    path("x/card/<uuid:id>/<str:size>", views.card_avatar_private, name="card_avatar_private"),
    path("x/gallery/<uuid:id>/<str:size>", views.gallery_private, name="gallery_private"),
]

