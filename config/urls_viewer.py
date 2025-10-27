from django.http import HttpResponse
from django.urls import path, re_path, include
from apps.media import urls as media_urls
from apps.cards import views_public as card_public
from apps.scheduling import views_public as booking_public
from apps.pages import urls_public as pages_public
from apps.delivery import views_public as delivery_public
from apps.search import views_public as search_views

urlpatterns = [
    path("img/", include((media_urls, "media"), namespace="media")),
    # Healthcheck endpoint for viewer
    path("healthz", lambda _request: HttpResponse("ok")),
    path("buscar/", search_views.nearby_page, name="search_nearby"),
    path("search/", include(("apps.search.urls", "search_public"), namespace="search")),
    # Legal pages in public viewer
    path("", include((pages_public, "pages"), namespace="pages")),
    # Auth endpoints for login/signup in the public viewer
    path("auth/", include(("apps.accounts.auth_urls", "accounts"), namespace="accounts")),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/?$", card_public.card_public, name="card_public"),
    path("", include(("apps.viewer.urls", "viewer"), namespace="viewer")),
    # Delivery viewer endpoints
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/item/(?P<slug>[a-z0-9\-_.]{1,160})$", delivery_public.item_modal, name="delivery_item_modal"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/cart$", delivery_public.cart_drawer, name="delivery_cart"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/cart/sidebar$", delivery_public.cart_sidebar, name="delivery_cart_sidebar"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/cart/add$", delivery_public.cart_add, name="delivery_cart_add"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/cart/update$", delivery_public.cart_update, name="delivery_cart_update"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/checkout$", delivery_public.checkout_form, name="delivery_checkout_form"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/checkout/submit$", delivery_public.checkout_submit, name="delivery_checkout_submit"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/cep$", delivery_public.cep_lookup_public, name="delivery_cep_lookup"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/checkout/send-code$", delivery_public.delivery_send_code, name="delivery_send_code"),
    re_path(r"^@(?P<nickname>[a-z0-9_.]{3,32})/checkout/verify-code$", delivery_public.delivery_verify_code, name="delivery_verify_code"),
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

# Custom error handlers
handler404 = "config.views_errors.handler404"
