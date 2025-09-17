from django.shortcuts import render, get_object_or_404
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
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


# Landing page (single-file template)
def home(request):
    return render(request, "pages/home.html")


@csrf_exempt
def lead(request: HttpRequest) -> HttpResponse:
    """Recebe leads de newsletter/contato via HTMX.

    Sucesso: retorna 204 com header HX-Trigger para toasts.
    Erro: retorna 400/422 com HX-Trigger amigável.
    """
    if request.method != "POST":
        resp = HttpResponse("Method not allowed", status=405)
        resp["Allow"] = "POST"
        return resp

    form_kind = (request.POST.get("form") or "").strip().lower()
    email = (request.POST.get("email") or "").strip()

    if form_kind == "newsletter":
        if not email:
            return _flash_error("Forneça um e-mail válido.")
        # Aqui você poderia persistir em um modelo ou provider de mailing.
        return _flash_success()

    if form_kind == "contato":
        name = (request.POST.get("name") or "").strip()
        message = (request.POST.get("message") or "").strip()
        if not (name and email and message):
            return _flash_error("Preencha nome, e-mail e mensagem.")
        # Aqui você poderia enfileirar e-mail/Slack/DB.
        return _flash_success()

    return _flash_error("Formulário inválido.", status=422)


def _flash_success() -> HttpResponse:
    resp = HttpResponse(status=204)
    resp["HX-Trigger"] = (
        '{"flash":{"type":"success","title":"Pronto!","message":"Recebemos seus dados."}}'
    )
    return resp


def _flash_error(message: str, status: int = 400) -> HttpResponse:
    resp = HttpResponse(status=status)
    resp["HX-Trigger"] = (
        f'{{"flash":{{"type":"error","title":"Ops","message":"{message}"}}}}'
    )
    return resp
