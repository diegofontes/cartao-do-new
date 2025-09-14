from django.urls import path, re_path, include
from apps.media import urls as media_urls
from apps.cards import views_public as card_public
from apps.scheduling import views_public as booking_public

urlpatterns = [
    path("img/", include((media_urls, "media"), namespace="media")),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/?$", card_public.card_public, name="card_public"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/slots$", booking_public.public_slots, name="public_slots"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/appointments$", booking_public.public_create_appointment, name="public_create_appointment"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/book$", booking_public.public_book_modal, name="public_book_modal"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/tabs/links$", card_public.tabs_links, name="tabs_links"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/tabs/gallery$", card_public.tabs_gallery, name="tabs_gallery"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/tabs/services$", card_public.tabs_services, name="tabs_services"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/services/(?P<id>[0-9a-f\-]{36})/sidebar$", booking_public.public_service_sidebar, name="public_service_sidebar"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/services/(?P<id>[0-9a-f\-]{36})/send-code$", booking_public.public_send_code, name="public_send_code"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/services/(?P<id>[0-9a-f\-]{36})/verify-code$", booking_public.public_verify_code, name="public_verify_code"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/services/(?P<id>[0-9a-f\-]{36})/validate$", booking_public.public_validate_booking, name="public_validate_booking"),
]
