from django.utils import timezone
import json
import re
import urllib.request
from uuid import uuid4
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST
from django.core.cache import cache
from .models import Card, LinkButton, CardAddress, GalleryItem, SocialLink, PLATFORM_CHOICES
from apps.common.images import process_avatar, process_gallery
from apps.billing.services import has_active_payment_method
from django.conf import settings
import re
from django.utils.text import slugify


@ensure_csrf_cookie
@login_required
def list_cards(request):
    cards = Card.objects.filter(owner=request.user).order_by("-created_at")
    return render(request, "cards/list.html", {"cards": cards, "viewer_base": getattr(settings, "VIEWER_BASE_URL", "http://localhost:9000")})


@login_required
def create_card(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        description = (request.POST.get("description") or "").strip()
        if len(title) < 3:
            return HttpResponseBadRequest("Invalid title")
        # Auto-generate slug unique per owner (no form field)
        base = slugify(title) or "card"
        candidate = base
        i = 2
        while Card.objects.filter(owner=request.user, slug=candidate).exists():
            candidate = f"{base}-{i}"
            i += 1
        card = Card.objects.create(owner=request.user, title=title, description=description, slug=candidate)
        return redirect("cards:detail", id=card.id)
    return render(request, "cards/create.html")


@login_required
def edit_card(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        description = (request.POST.get("description") or "").strip()
        if len(title) < 3:
            return HttpResponseBadRequest("Invalid title")
        card.title = title
        card.description = description
        card.save(update_fields=["title", "description"])
        return redirect("cards:detail", id=card.id)
    return render(request, "cards/edit.html", {"card": card})


@ensure_csrf_cookie
@login_required
def card_detail(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    return render(request, "cards/detail.html", {"card": card, "viewer_base": getattr(settings, "VIEWER_BASE_URL", "http://localhost:9000")})


@login_required
def publish_card(request, id):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    card = get_object_or_404(Card, id=id)
    if card.owner != request.user:
        return HttpResponseForbidden("Not allowed")
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
    except Exception:
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
    label = request.POST.get("label", "").strip()
    url = request.POST.get("url", "").strip()
    if not label or not url:
        return HttpResponseBadRequest("label and url required")
    LinkButton.objects.create(card=card, label=label, url=url)
    return links_partial(request, id)


@login_required
@require_POST
def delete_link(request, link_id):
    link = get_object_or_404(LinkButton, id=link_id, card__owner=request.user)
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
    label = (request.POST.get("label", "") or "").strip()
    if not label:
        return HttpResponseBadRequest("label required")
    cep = (request.POST.get("cep", "") or "").strip()
    norm = re.sub(r"\D", "", cep)
    if not re.fullmatch(r"\d{8}", norm):
        return HttpResponseBadRequest("CEP inválido")
    CardAddress.objects.create(
        card=card,
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
    return addresses_partial(request, id)


@login_required
@require_POST
def delete_address(request, address_id):
    addr = get_object_or_404(CardAddress, id=address_id, card__owner=request.user)
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
    items = GalleryItem.objects.filter(card=card).order_by("order", "created_at")
    return render(request, "cards/_gallery.html", {"card": card, "items": items})


@login_required
@require_POST
def add_gallery_item(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    files = request.FILES.getlist("files") or ([] if request.FILES.get("file") is None else [request.FILES.get("file")])
    if not files:
        return HttpResponseBadRequest("file required")
    errors = []
    for f in files:
        ctype = getattr(f, "content_type", "") or ""
        size = getattr(f, "size", 0) or 0
        if not ctype.startswith("image/"):
            errors.append(f"Arquivo inválido: {getattr(f,'name','arquivo')} (MIME)")
            continue
        if size > 5 * 1024 * 1024:
            errors.append(f"Arquivo muito grande: {getattr(f,'name','arquivo')} (>5MB)")
            continue
        # Process and store thumbs
        out = process_gallery(card.owner_id, f)
        GalleryItem.objects.create(
            card=card,
            file=out["orig"],
            thumb_w256=out["w256"],
            thumb_w768=out["w768"],
            caption=request.POST.get("caption", ""),
        )
    ctx = {"card": card, "items": GalleryItem.objects.filter(card=card).order_by("order", "created_at"), "errors": errors}
    return render(request, "cards/_gallery.html", ctx)


@login_required
@require_POST
def delete_gallery_item(request, item_id):
    it = get_object_or_404(GalleryItem, id=item_id, card__owner=request.user)
    cid = it.card.id
    it.delete()
    return gallery_partial(request, cid)


@login_required
@require_POST
def delete_card(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    card.delete()
    # Support HTMX redirect
    if request.headers.get("HX-Request"):
        resp = HttpResponse("")
        resp["HX-Redirect"] = "/cards/"
        return resp
    return redirect("cards:list")


@login_required
@require_POST
def upload_avatar(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    f = request.FILES.get("avatar")
    if not f:
        return HttpResponseBadRequest("file required")
    ctype = getattr(f, "content_type", "")
    size = getattr(f, "size", 0)
    if not (ctype.startswith("image/jpeg") or ctype.startswith("image/png") or ctype.startswith("image/webp")):
        return HttpResponseBadRequest("unsupported type")
    if size > 5 * 1024 * 1024:
        return HttpResponseBadRequest("too large")
    out = process_avatar(card.owner_id, f)
    card.avatar = out["orig"]
    card.avatar_w64 = out["w64"]
    card.avatar_w128 = out["w128"]
    card.avatar_hash = out["hash"]
    card.avatar_rev = (card.avatar_rev or 0) + 1
    card.save(update_fields=["avatar", "avatar_w64", "avatar_w128", "avatar_hash", "avatar_rev"])
    return render(request, "cards/_card_header.html", {"card": card})


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
    cid = sl.card.id
    sl.delete()
    return social_links_partial(request, cid)


# ---- HTMX Partial: Tabs order ----
@login_required
def tabs_partial(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    allowed = ["links", "gallery", "services"]
    order = [k for k in (card.tabs_order or "links,gallery,services").split(",") if k in allowed]
    # Normalize to full permutation if missing any
    for k in allowed:
        if k not in order:
            order.append(k)
    return render(request, "cards/_tabs.html", {"card": card, "current": order})


@login_required
@require_POST
def set_tabs_order(request, id):
    card = get_object_or_404(Card, id=id, owner=request.user)
    raw = (request.POST.get("tabs_order") or "").strip()
    allowed = ["links", "gallery", "services"]
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
