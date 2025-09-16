from django.shortcuts import render, get_object_or_404
from .models import LegalPage


def _page(slug: str) -> LegalPage:
    return get_object_or_404(LegalPage, slug=slug, is_active=True)


# Main app pages (extends base.html)
def privacy_app(request):
    page = _page("politica_de_privacidade")
    return render(request, "pages/legal_app.html", {"page": page})


def terms_app(request):
    page = _page("termos_de_uso")
    return render(request, "pages/legal_app.html", {"page": page})


# Public viewer pages (extends public/base_public.html)
def privacy_public(request):
    page = _page("politica_de_privacidade")
    return render(request, "public/legal_public.html", {"page": page})


def terms_public(request):
    page = _page("termos_de_uso")
    return render(request, "public/legal_public.html", {"page": page})

