import json
from pprint import pprint
import re
from django.utils import timezone
import urllib.request
from uuid import uuid4
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST
from itertools import permutations
from django.core.cache import cache
from .models import Card, LinkButton, CardAddress, GalleryItem, SocialLink, PLATFORM_CHOICES
from .markdown import MAX_MARKDOWN_CHARS, has_about_content, sanitize_about_markdown
from apps.common.images import process_avatar, process_gallery
from apps.common.validators import validate_upload
from django.core.exceptions import ValidationError
from .services import add_link as svc_add_link, add_address as svc_add_address, add_gallery_item as svc_add_gallery
from apps.billing.services import has_active_payment_method
from django.conf import settings
from django.utils.text import slugify
from apps.scheduling.models import SchedulingService

TAB_LABELS = {
    "menu": "Cardápio",
    "links": "Links",
    "gallery": "Galeria",
    "services": "Serviços",
    "about": "Sobre",
}


def _allowed_tabs_for(card: Card) -> tuple[list[str], str]:
    if getattr(card, "mode", "appointment") == "delivery":
        base_allowed = ["menu", "links", "gallery"]
        default_order = "menu,links,gallery"
    else:
        base_allowed = ["links", "gallery", "services"]
        default_order = "links,gallery,services"
    allowed = list(base_allowed)
    if has_about_content(card.about_markdown):
        allowed.append("about")
        default_order = f"{default_order},about"
    return allowed, default_order


def _tab_options(allowed: list[str]) -> list[tuple[str, str]]:
    opts: list[tuple[str, str]] = []
    for perm in permutations(allowed):
        value = ",".join(perm)
        label = ", ".join(TAB_LABELS.get(key, key.title()) for key in perm)
        opts.append((value, label))
    return opts


@ensure_csrf_cookie
@login_required
def list_cards(request):
    show_archived = str(request.GET.get("show_archived") or "").lower() in ("1", "true", "yes", "on")
    qs = Card.objects.filter(owner=request.user)
    if not show_archived:
        qs = qs.exclude(status="archived")
    cards = qs.order_by("-created_at")
    return render(request, "cards/list.html", {"cards": cards, "show_archived": show_archived, "viewer_base": getattr(settings, "VIEWER_BASE_URL", "http://localhost:9000")})


@login_required
def create_card(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = (request.POST.get("description") or "").strip()
        raw_phone = (request.POST.get("notification_phone") or "").strip()
        if len(title) < 3:
            return HttpResponseBadRequest("Invalid title")
        # Auto-generate slug unique per owner (no form field)
        base = slugify(title) or "card"
        candidate = base
        i = 2
        while Card.objects.filter(owner=request.user, slug=candidate).exists():
            candidate = f"{base}-{i}"
            i += 1
        mode = request.POST.get("mode") or "appointment"
        if mode not in {"appointment", "delivery"}:
            mode = "appointment"
        # Normalize optional phone
        from apps.common.phone import to_e164
        notification_phone = None
        if raw_phone:
            try:
                notification_phone = to_e164(raw_phone, "BR")
            except Exception:
                return HttpResponseBadRequest("Telefone inválido")
        card = Card.objects.create(owner=request.user, title=title, description=description, slug=candidate, mode=mode, notification_phone=notification_phone)
        return redirect("cards:detail", id=card.id)
    return render(request, "cards/create.html")


@login_required
def edit_card(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        if request.method == "POST":
            return HttpResponseForbidden("Card marked for deactivation")
        return render(request, "cards/edit.html", {"card": card, "deactivation_blocked": True})
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        mode = (request.POST.get("mode") or card.mode or "appointment").strip()
        raw_phone = (request.POST.get("notification_phone") or "").strip()
        if len(title) < 3:
            return HttpResponseBadRequest("Invalid title")
        # Normalize mode
        if mode not in {"appointment", "delivery"}:
            mode = card.mode or "appointment"
        # If switching modes, optionally normalize tabs_order defaults
        changing_mode = (mode != (card.mode or "appointment"))
        card.title = title
        card.description = description
        card.mode = mode
        update_fields = ["title", "description", "mode"]
        # Normalize and set notification phone (optional)
        from apps.common.phone import to_e164
        if raw_phone:
            try:
                card.notification_phone = to_e164(raw_phone, "BR")
            except Exception:
                return HttpResponseBadRequest("Telefone inválido")
        else:
            card.notification_phone = None
        update_fields.append("notification_phone")
        # Adjust tabs order only if it matches the previous default or empty
        prev_default = "links,gallery,services"
        new_default = "menu,links,gallery"
        current_tabs = (card.tabs_order or prev_default)
        if changing_mode:
            if mode == "delivery" and current_tabs in {"", prev_default}:
                card.tabs_order = new_default
                update_fields.append("tabs_order")
            elif mode == "appointment" and current_tabs in {"", new_default}:
                card.tabs_order = prev_default
                update_fields.append("tabs_order")
        card.save(update_fields=update_fields)
        return redirect("cards:detail", id=card.id)
    return render(request, "cards/edit.html", {"card": card})


@ensure_csrf_cookie
@login_required
def card_detail(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    return render(request, "cards/detail.html", {"card": card, "viewer_base": getattr(settings, "VIEWER_BASE_URL", "http://localhost:9000")})


@login_required
def about_partial(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    preview_html = ""
    error = None
    try:
        preview_html = sanitize_about_markdown(card.about_markdown or "")
    except ValueError as exc:  # pragma: no cover - persisted content should already be valid
        error = str(exc)
    ctx = {
        "card": card,
        "about_markdown": card.about_markdown or "",
        "preview_html": preview_html,
        "error": error,
        "max_chars": MAX_MARKDOWN_CHARS,
    }
    return render(request, "cards/_about.html", ctx)


@login_required
@require_POST
def preview_about(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    markdown_value = (request.POST.get("about_markdown") or "").strip()
    try:
        preview_html = sanitize_about_markdown(markdown_value)
        status = 200
        error = None
    except ValueError as exc:
        preview_html = ""
        error = str(exc)
        status = 422
    resp = render(request, "cards/_about_preview.html", {"card": card, "preview_html": preview_html, "error": error})
    resp.status_code = status
    return resp


@login_required
@require_POST
def save_about(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    markdown_value = (request.POST.get("about_markdown") or "").strip()
    try:
        preview_html = sanitize_about_markdown(markdown_value)
    except ValueError as exc:
        resp = render(
            request,
            "cards/_about.html",
            {
                "card": card,
                "about_markdown": markdown_value,
                "preview_html": "",
                "error": str(exc),
                "max_chars": MAX_MARKDOWN_CHARS,
            },
        )
        resp.status_code = 422
        return resp
    card.about_markdown = markdown_value
    card.save(update_fields=["about_markdown"])
    ctx = {
        "card": card,
        "about_markdown": markdown_value,
        "preview_html": preview_html,
        "error": None,
        "max_chars": MAX_MARKDOWN_CHARS,
    }
    resp = render(request, "cards/_about.html", ctx)
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Sobre atualizado", "message": "Conteúdo salvo."}})
    return resp


@login_required
def publish_card(request, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    card = get_object_or_404(Card, id=id)
    pprint(card)
    if card.owner != request.user:
        return HttpResponseForbidden("Not allowed")
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    if card.status == "published":
        return HttpResponse("already published", status=409)
    # Payment check
    if not has_active_payment_method(request.user):
        return HttpResponse("payment required", status=402)
    nickname = (request.POST.get("nickname") or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_.]{3,32}", nickname or ""):
        return HttpResponse("invalid nickname", status=422)
    if nickname in getattr(settings, "RESERVED_NICKNAMES", set()):
        return HttpResponse("reserved nickname", status=422)
    # availability (case-insensitive)
    exists = Card.objects.filter(nickname__iexact=nickname).exclude(id=card.id).exists()
    if exists:
        return HttpResponse("nickname taken", status=409)
    # business rule: additional validations
    try:
        if not card.can_publish():
            return HttpResponse("card not ready", status=422)
        card.nickname = nickname
        card.status = "published"
        card.published_at = timezone.now()
        card.save(update_fields=["nickname", "status", "published_at"])
    except Exception as e:
        pprint(e)
        return HttpResponse("publish failed", status=400)
    # Redirect to public URL
    response = HttpResponse("")
    response["HX-Redirect"] = f"/@{nickname}"
    return response


@login_required
def publish_modal(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    has_pm = has_active_payment_method(request.user)
    return render(request, "cards/_publish_modal.html", {"card": card, "has_pm": has_pm})


def check_nickname(request):
    raw = request.GET.get("value") or request.GET.get("nickname") or ""
    value = raw.strip().lower()
    ok = bool(re.fullmatch(r"[a-z0-9_.]{3,32}", value)) and (value not in getattr(settings, "RESERVED_NICKNAMES", set()))
    available = ok and (not Card.objects.filter(nickname__iexact=value).exists())
    if request.headers.get("HX-Request"):
        # Return human‑readable inline feedback for the modal (status 200 to avoid noisy errors)
        if not ok:
            return HttpResponse("Inválido: use letras minúsculas, números, _ ou . (3–32)")
        return HttpResponse("Disponível" if available else "Indisponível")
    return JsonResponse({"available": available, "ok": ok})


# ---- HTMX Partials: Links ----
@login_required
def links_partial(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    links = LinkButton.objects.filter(card=card).order_by("order", "created_at")
    return render(request, "cards/_links.html", {"card": card, "links": links})


@login_required
@require_POST
def add_link(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    label = request.POST.get("label", "").strip()
    url = request.POST.get("url", "").strip()
    if not label or not url:
        return HttpResponseBadRequest("label and url required")
    try:
        svc_add_link(card, label=label, url=url)
    except ValidationError as e:
        resp = links_partial(request, id)
        resp.status_code = 422
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Limite atingido", "message": str(e)}})
        return resp
    resp = links_partial(request, id)
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Feito!", "message": "Link adicionado."}})
    return resp


@login_required
@require_POST
def delete_link(request, link_id):
    link = get_object_or_404(LinkButton, id=link_id, card__owner=request.user)
    if getattr(link.card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    card_id = link.card.id
    link.delete()
    return links_partial(request, card_id)


# ---- HTMX Partials: Addresses ----
@login_required
def addresses_partial(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    addresses = card.addresses.all().order_by("created_at")
    return render(request, "cards/_addresses.html", {"card": card, "addresses": addresses})


@login_required
@require_POST
def add_address(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    label = (request.POST.get("label", "") or "").strip()
    if not label:
        return HttpResponseBadRequest("label required")
    cep = (request.POST.get("cep", "") or "").strip()
    norm = re.sub(r"\D", "", cep)
    if not re.fullmatch(r"\d{8}", norm):
        return HttpResponseBadRequest("CEP inválido")
    try:
        svc_add_address(
            card,
            label=label,
            cep=f"{norm[:5]}-{norm[5:]}",
            logradouro=(request.POST.get("logradouro", "") or "").strip(),
            numero=(request.POST.get("numero", "") or "").strip(),
            complemento=(request.POST.get("complemento", "") or "").strip(),
            bairro=(request.POST.get("bairro", "") or "").strip(),
            cidade=(request.POST.get("cidade", "") or "").strip(),
            uf=(request.POST.get("uf", "") or "").strip().upper(),
            pais=(request.POST.get("pais", "BR") or "BR").upper(),
        )
    except ValidationError as e:
        resp = addresses_partial(request, id)
        resp.status_code = 422
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Limite atingido", "message": str(e)}})
        return resp
    resp = addresses_partial(request, id)
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Feito!", "message": "Endereço adicionado."}})
    return resp


@login_required
@require_POST
def delete_address(request, address_id):
    addr = get_object_or_404(CardAddress, id=address_id, card__owner=request.user)
    if getattr(addr.card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    card_id = addr.card.id
    addr.delete()
    return addresses_partial(request, card_id)


@login_required
def address_form(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    return render(request, "cards/_address_form.html", {"card": card})


@login_required
def cep_lookup(request):
    cep = (request.GET.get("cep") or "").strip()
    norm = re.sub(r"\D", "", cep)
    if not re.fullmatch(r"\d{8}", norm):
        return render(request, "cards/_address_fields.html", {"error": "CEP inválido."})
    cache_key = f"cep:{norm}"
    data = cache.get(cache_key)
    if not data:
        try:
            with urllib.request.urlopen(f"https://viacep.com.br/ws/{norm}/json/", timeout=4) as resp:
                raw = resp.read()
                jd = json.loads(raw.decode("utf-8"))
        except Exception:
            jd = {}
        if jd and not jd.get("erro"):
            data = {
                "logradouro": jd.get("logradouro") or "",
                "bairro": jd.get("bairro") or "",
                "cidade": jd.get("localidade") or "",
                "uf": (jd.get("uf") or "").upper(),
            }
            cache.set(cache_key, data, 60 * 60 * 24)
    if not data:
        return render(request, "cards/_address_fields.html", {"error": "CEP não encontrado ou indisponível."})
    return render(request, "cards/_address_fields.html", data)


# ---- HTMX Partials: Gallery ----
@login_required
def gallery_partial(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    items = GalleryItem.objects.filter(card=card).order_by("importance", "order", "created_at")
    services = SchedulingService.objects.filter(card=card).order_by("name")
    return render(request, "cards/_gallery.html", {"card": card, "items": items, "services": services})


@login_required
@require_POST
def add_gallery_item(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    files = request.FILES.getlist("files") or ([] if request.FILES.get("file") is None else [request.FILES.get("file")])
    if not files:
        return HttpResponseBadRequest("file required")
    errors = []
    for f in files:
        # Size check to return 413 specifically
        max_bytes = getattr(settings, "MAX_UPLOAD_BYTES", 2 * 1024 * 1024)
        if getattr(f, "size", 0) > max_bytes:
            ctx = {
                "card": card,
                "items": GalleryItem.objects.filter(card=card).order_by("importance", "order", "created_at"),
                "errors": ["Arquivo excede 2MB."],
                "services": SchedulingService.objects.filter(card=card).order_by("name"),
            }
            resp = render(request, "cards/_gallery.html", ctx)
            resp.status_code = 413
            resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Upload bloqueado", "message": "Arquivo excede 2MB."}})
            return resp
        try:
            validate_upload(f)
        except ValidationError as e:
            errors.append(str(e))
            continue
        # Process and store thumbs
        try:
            out = process_gallery(card.owner_id, f)
            svc_add_gallery(
                card,
                file=out["orig"],
                thumb_w256=out["w256"],
                thumb_w768=out["w768"],
                caption=request.POST.get("caption", ""),
            )
        except ValidationError as e:
            errors.append(str(e))
            continue
    ctx = {
        "card": card,
        "items": GalleryItem.objects.filter(card=card).order_by("importance", "order", "created_at"),
        "errors": errors,
        "services": SchedulingService.objects.filter(card=card).order_by("name"),
    }
    resp = render(request, "cards/_gallery.html", ctx)
    if errors:
        resp.status_code = 422
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Upload bloqueado", "message": "; ".join(errors)}})
    else:
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Feito!", "message": "Upload concluído."}})
    return resp


@login_required
@require_POST
def delete_gallery_item(request, item_id):
    it = get_object_or_404(GalleryItem, id=item_id, card__owner=request.user)
    if getattr(it.card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    cid = it.card.id
    it.delete()
    return gallery_partial(request, cid)


@login_required
@require_POST
def update_gallery_item(request, item_id):
    item = get_object_or_404(GalleryItem, id=item_id, card__owner=request.user)
    card = item.card
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    errors: list[str] = []
    caption = (request.POST.get("caption") or "").strip()
    visible = "visible_in_gallery" in request.POST
    raw_importance = (request.POST.get("importance") or "").strip() or str(item.importance)
    try:
        importance = int(raw_importance)
    except ValueError:
        errors.append("Ordem de importância deve ser um número inteiro.")
        importance = item.importance
    if importance < 1:
        errors.append("Ordem de importância deve ser no mínimo 1.")
    service_id = (request.POST.get("service") or "").strip()
    service = None
    if service_id:
        try:
            service = SchedulingService.objects.get(id=service_id, card=card)
        except SchedulingService.DoesNotExist:
            errors.append("Serviço inválido para este cartão.")
    item.caption = caption
    item.visible_in_gallery = visible
    item.importance = importance
    item.service = service
    success = False
    if not errors:
        try:
            item.full_clean()
        except ValidationError as e:
            errors.extend([str(msg) for msg in e.messages])
    if not errors:
        item.save(update_fields=["caption", "visible_in_gallery", "importance", "service"])
        success = True
    ctx = {
        "card": card,
        "items": GalleryItem.objects.filter(card=card).order_by("importance", "order", "created_at"),
        "services": SchedulingService.objects.filter(card=card).order_by("name"),
        "errors": errors,
    }
    resp = render(request, "cards/_gallery.html", ctx)
    if errors:
        resp.status_code = 422
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Erro", "message": "; ".join(errors)}})
    elif success:
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Feito!", "message": "Configurações atualizadas."}})
    return resp


"""Delete card endpoint removed: archiving is the supported flow."""


@login_required
@require_POST
def upload_avatar(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    f = request.FILES.get("avatar")
    if not f:
        return HttpResponseBadRequest("file required")
    max_bytes = getattr(settings, "MAX_UPLOAD_BYTES", 2 * 1024 * 1024)
    if getattr(f, "size", 0) > max_bytes:
        resp = render(request, "cards/_card_header.html", {"card": card})
        resp.status_code = 413
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Upload bloqueado", "message": "Arquivo excede 2MB."}})
        return resp
    try:
        validate_upload(f)
    except ValidationError as e:
        resp = render(request, "cards/_card_header.html", {"card": card})
        resp.status_code = 415 if "Tipo de arquivo" in str(e) else 422
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Upload bloqueado", "message": str(e)}})
        return resp
    out = process_avatar(card.owner_id, f)
    card.avatar = out["orig"]
    card.avatar_w64 = out["w64"]
    card.avatar_w128 = out["w128"]
    card.avatar_hash = out["hash"]
    card.avatar_rev = (card.avatar_rev or 0) + 1
    card.save(update_fields=["avatar", "avatar_w64", "avatar_w128", "avatar_hash", "avatar_rev"])
    resp = render(request, "cards/_card_header.html", {"card": card})
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Feito!", "message": "Avatar atualizado."}})
    return resp


# ---- HTMX Partials: Social Links ----
@login_required
def social_links_partial(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    links = SocialLink.objects.filter(card=card, is_active=True).order_by("order", "created_at")
    return render(request, "cards/_social_links.html", {"card": card, "links": links, "platforms": PLATFORM_CHOICES})


def _normalize_social_url(platform: str, handle_or_url: str) -> str:
    s = handle_or_url.strip()
    if platform == "instagram":
        if s.startswith("http"):
            return s
        return f"https://instagram.com/{s.lstrip('@')}"
    if platform == "facebook":
        if s.startswith("http"):
            return s
        return f"https://facebook.com/{s}"
    if platform == "linkedin":
        if s.startswith("http"):
            return s
        return f"https://www.linkedin.com/in/{s}"
    if platform == "whatsapp":
        digits = re.sub(r"\D", "", s)
        return f"https://wa.me/{digits}"
    if platform == "x":
        if s.startswith("http"):
            return s
        return f"https://x.com/{s.lstrip('@')}"
    if platform == "tiktok":
        if s.startswith("http"):
            return s
        return f"https://www.tiktok.com/@{s.lstrip('@')}"
    if platform == "youtube":
        return s
    if platform == "github":
        if s.startswith("http"):
            return s
        return f"https://github.com/{s}"
    if platform == "site":
        return s
    return s


@login_required
@require_POST
def add_social_link(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    platform = request.POST.get("platform") or ""
    handle = request.POST.get("handle_or_url") or ""
    label = request.POST.get("label") or ""
    if platform not in dict(PLATFORM_CHOICES):
        return HttpResponseBadRequest("Plataforma inválida")
    url = _normalize_social_url(platform, handle)
    if any(bad in url for bad in ["javascript:", "data:"]):
        return HttpResponseBadRequest("URL inválida")
    SocialLink.objects.create(card=card, platform=platform, url=url, label=label)
    return social_links_partial(request, id)


@login_required
@require_POST
def delete_social_link(request, link_id):
    sl = get_object_or_404(SocialLink, id=link_id, card__owner=request.user)
    if getattr(sl.card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    cid = sl.card.id
    sl.delete()
    return social_links_partial(request, cid)


# ---- HTMX Partial: Tabs order ----
@login_required
def tabs_partial(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    allowed, default_order = _allowed_tabs_for(card)
    order = [k for k in (card.tabs_order or default_order).split(",") if k in allowed]
    # Normalize to full permutation if missing any
    for k in allowed:
        if k not in order:
            order.append(k)
    options = _tab_options(allowed)
    return render(
        request,
        "cards/_tabs.html",
        {
            "card": card,
            "current": order,
            "options": options,
            "has_about": "about" in allowed,
        },
    )


@login_required
@require_POST
def set_tabs_order(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    raw = (request.POST.get("tabs_order") or "").strip()
    allowed, _ = _allowed_tabs_for(card)
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    # accept values like "links,gallery,services" or space separated
    if not parts and raw:
        parts = [p.strip() for p in raw.split() if p.strip()]
    # validate permutation
    if sorted(parts) != sorted(allowed):
        # try from select option like "services,links,gallery"
        return HttpResponseBadRequest("Ordem inválida")
    card.tabs_order = ",".join(parts)
    card.save(update_fields=["tabs_order"])
    return tabs_partial(request, id)


# ---- Deactivation / Reactivation ----
@login_required
@require_POST
def mark_deactivation(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    if card.status != "published":
        return HttpResponseBadRequest("only published cards can be marked")
    if not getattr(card, "deactivation_marked", False):
        card.deactivation_marked = True
        card.deactivation_marked_at = timezone.now()
        card.save(update_fields=["deactivation_marked", "deactivation_marked_at"])
    resp = HttpResponse("")
    resp["HX-Redirect"] = str(request.headers.get("Referer") or f"/cards/{card.id}/")
    return resp


@login_required
@require_POST
def reactivate(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        card.deactivation_marked = False
        card.deactivation_marked_at = None
        card.save(update_fields=["deactivation_marked", "deactivation_marked_at"])
    resp = HttpResponse("")
    resp["HX-Redirect"] = str(request.headers.get("Referer") or f"/cards/{card.id}/")
    return resp
