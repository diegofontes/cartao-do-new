from __future__ import annotations

from dataclasses import dataclass
import pprint
from typing import Any

from django.http import Http404, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from django.conf import settings
from django.db import transaction
from django.core.cache import cache
from django.urls import reverse
from apps.common.phone import to_e164, gen_code, hash_code
from apps.notifications.api import enqueue
import json, re, urllib.request

#from apps.cards.views_public import _get_card_by_nickname
from .models import MenuGroup, MenuItem, ModifierGroup, ModifierOption, Order, OrderItem, OrderItemOption, OrderItemText
from apps.cards.models import Card, LinkButton, GalleryItem, SocialLink
from apps.cards.markdown import has_about_content, sanitize_about_markdown

def _get_card_by_nickname(nickname: str) -> Card:
    q = Card.objects.filter(nickname__iexact=nickname, status="published", deactivation_marked=False)
    return get_object_or_404(q)


def _ensure_delivery_card(nickname: str):
    card = _get_card_by_nickname(nickname)
    if card.mode != "delivery":
        raise Http404()
    return card


@ensure_csrf_cookie
def menu_home(request, nickname: str):
    card = _ensure_delivery_card(nickname)
    groups = (
        MenuGroup.objects.filter(card=card, is_active=True)
        .order_by("order", "created_at")
    )
    # Tabs order: menu, links, gallery (customizable)
    about_html = ""
    about_enabled = False
    if has_about_content(card.about_markdown):
        try:
            about_html = sanitize_about_markdown(card.about_markdown or "")
            about_enabled = bool(about_html.strip())
        except ValueError:
            about_html = ""
            about_enabled = False
    allowed_base = ["menu", "links", "gallery"]
    if about_enabled:
        allowed_base.append("about")
    allowed = tuple(allowed_base)
    raw_order = (card.tabs_order or "menu,links,gallery")
    tab_order = [k.strip() for k in raw_order.split(',') if k.strip() in allowed]
    # Ensure menu tab is always present for delivery cards
    if "menu" not in tab_order:
        tab_order = ["menu"] + tab_order
    if about_enabled and "about" not in tab_order:
        tab_order.append("about")
    # Fallback to full default if still empty
    if not tab_order:
        tab_order = ["menu", "links", "gallery"]
        if about_enabled:
            tab_order.append("about")
    # Fetch links/gallery for tabs
    links = LinkButton.objects.filter(card=card).order_by("order", "created_at")
    gallery = GalleryItem.objects.filter(card=card, visible_in_gallery=True).order_by("importance", "order", "created_at")
    return render(
        request,
        "public/menu_public.html",
        {
            "card": card,
            "groups": groups,
            "tab_order": tab_order,
            "links": links,
            "gallery": gallery,
            "about_html": about_html,
            "about_enabled": about_enabled,
        },
    )


def item_modal(request, nickname: str, slug: str):
    card = _ensure_delivery_card(nickname)
    item = get_object_or_404(MenuItem, card=card, slug=slug, is_active=True)
    modifier_groups = item.modifier_groups.order_by("order", "created_at")
    return render(request, "public/_menu_item_modal.html", {"card": card, "item": item, "modifier_groups": modifier_groups})


def _cart_key(card_id: str) -> str:
    return f"cart:{card_id}"


def _get_cart(request, card_id: str) -> dict:
    return request.session.get(_cart_key(card_id), {"items": []})


def _save_cart(request, card_id: str, cart: dict) -> None:
    request.session[_cart_key(card_id)] = cart
    request.session.modified = True


def _session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def price_for_order_item(menu_item: MenuItem, selections: dict[str, Any]) -> int:
    """Compute unit price considering modifier groups with robust coercion.

    - For text groups: value is a short string (<=100 chars).
    - For single/multi: always treat selection as a list of option IDs (strings).
    """
    base = int(menu_item.base_price_cents or 0)
    delta = 0
    for group in menu_item.modifier_groups.order_by("order", "created_at").all():
        raw = selections.get(str(group.id)) if isinstance(selections, dict) else None
        if raw is None:
            raw = selections.get(group.id) if isinstance(selections, dict) else None

        if group.type == "text":
            val = raw
            if val is None:
                val = ""
            if not isinstance(val, str):
                val = str(val)
            # Truncate for safety
            val = val[:100]
            # Required text must be non-empty
            if group.required and len(val.strip()) == 0:
                raise ValueError("text group required")
            # No price impact for text groups
            continue
        else:
            # Normalize to list for single and multi
            if raw is None:
                sel_list: list[str] = []
            elif isinstance(raw, (list, tuple)):
                sel_list = [str(x) for x in raw if str(x)]
            else:
                sel_list = [str(raw)] if str(raw) else []
            # Deduplicate while preserving order
            seen = set()
            norm_sel: list[str] = []
            for x in sel_list:
                if x not in seen:
                    seen.add(x)
                    norm_sel.append(x)

            # Validate required/min/max
            if group.type == "single":
                if group.required and len(norm_sel) != 1:
                    raise ValueError("single group requires exactly one option")
                if not group.required and len(norm_sel) not in (0, 1):
                    raise ValueError("single group max 1 option")
            elif group.type == "multi":
                n = len(norm_sel)
                min_c = int(group.min_choices or 0)
                max_c = int(group.max_choices) if group.max_choices is not None else n
                if n < min_c or n > max_c:
                    raise ValueError("multi group min/max not satisfied")

            # Sum deltas for valid options
            if norm_sel:
                for opt_id in norm_sel:
                    opt = ModifierOption.objects.filter(pk=opt_id, modifier_group=group, is_active=True).first()
                    if not opt:
                        raise ValueError("invalid option")
                    delta += int(opt.price_delta_cents or 0)
    return int(base) + int(delta)


@require_http_methods(["POST"])  # CSRF enforced
def cart_add(request, nickname: str):
    
    card = _ensure_delivery_card(nickname)
    item_id = request.POST.get("item_id")
    qty = int(request.POST.get("qty", "1"))
    if qty < 1:
        qty = 1
    item = get_object_or_404(MenuItem, card=card, pk=item_id, is_active=True)
    
    print("cart_add", item)
    # Collect selections as group_id -> list or text
    selections: dict[str, Any] = {}
    for key, val in request.POST.items():
        if key.startswith("mg_"):
            gid = key[3:]
            if val:
                selections[gid] = val
    # HTMX can send multi values via mg_<id>
    for key in request.POST.getlist("_mg_multi"):
        pass  # Not used; rely on mg_<id>[]= when applicable

    # Normalize multi-values
    # If inputs are sent as mg_<gid> for singles or mg_<gid> for multi with multiple values
    normalized: dict[str, Any] = {}
    for key in request.POST:
        if key.startswith("mg_"):
            gid = key[3:]
            vals = request.POST.getlist(key)
            normalized[gid] = vals if len(vals) > 1 else (vals[0] if vals else "")

    # Price validation (raises if invalid)
    try:
        unit_price = price_for_order_item(item, normalized)
    except Exception as e:
        return JsonResponse({"flash": {"type": "error", "title": "Ops", "message": "Revise suas escolhas."}}, status=422)

    cart = _get_cart(request, str(card.id))
    cart["items"].append({
        "item_id": str(item.id),
        "qty": qty,
        "selections": normalized,
    })
    _save_cart(request, str(card.id), cart)
    # Prefer updating the sidebar cart when available
    return render(request, "public/_cart_sidebar.html", {"card": card, "cart": _recalc_cart(card, cart)})


@require_http_methods(["POST"])  # CSRF enforced
def cart_update(request, nickname: str):
    card = _ensure_delivery_card(nickname)
    index = int(request.POST.get("index", "-1"))
    qty = int(request.POST.get("qty", "0"))
    cart = _get_cart(request, str(card.id))
    if 0 <= index < len(cart.get("items", [])):
        if qty <= 0:
            del cart["items"][index]
        else:
            cart["items"][index]["qty"] = qty
    _save_cart(request, str(card.id), cart)
    return render(request, "public/_cart_sidebar.html", {"card": card, "cart": _recalc_cart(card, cart)})


def cart_drawer(request, nickname: str):
    card = _ensure_delivery_card(nickname)
    cart = _get_cart(request, str(card.id))
    return render(request, "public/_cart_sidebar.html", {"card": card, "cart": _recalc_cart(card, cart)})


def cart_sidebar(request, nickname: str):
    card = _ensure_delivery_card(nickname)
    cart = _get_cart(request, str(card.id))
    return render(request, "public/_cart_sidebar.html", {"card": card, "cart": _recalc_cart(card, cart)})


def _recalc_cart(card, cart: dict) -> dict:
    items_out = []
    subtotal = 0
    for entry in cart.get("items", []):
        item = get_object_or_404(MenuItem, card=card, pk=entry["item_id"], is_active=True)
        price = price_for_order_item(item, entry.get("selections") or {})
        line = price * int(entry.get("qty", 1))
        items_out.append({
            "item": item,
            "qty": int(entry.get("qty", 1)),
            "unit_price_cents": price,
            "line_subtotal_cents": line,
            "selections": entry.get("selections") or {},
        })
        subtotal += line
    return {"items": items_out, "subtotal_cents": subtotal}


def checkout_form(request, nickname: str):
    card = _ensure_delivery_card(nickname)
    cart = _get_cart(request, str(card.id))
    cart_calc = _recalc_cart(card, cart)
    return render(request, "public/_checkout_slideover.html", {"card": card, "cart": cart_calc, "phone_verified": bool(request.session.get("delivery_phone_verified"))})


def _gen_order_code(card_id: str) -> str:
    import secrets, string
    alphabet = string.ascii_uppercase + string.digits
    return "#" + "".join(secrets.choice(alphabet) for _ in range(4))


@require_http_methods(["POST"])  # CSRF enforced
@transaction.atomic
def checkout_submit(request, nickname: str):
    card = _ensure_delivery_card(nickname)
    cart = _get_cart(request, str(card.id))
    calc = _recalc_cart(card, cart)
    if not calc["items"]:
        return JsonResponse({"flash": {"type": "error", "title": "Carrinho vazio", "message": "Adicione itens."}}, status=422)

    # Basic form fields
    name = (request.POST.get("name") or "").strip()
    phone_raw = (request.POST.get("phone") or "").strip()
    email = (request.POST.get("email") or "").strip()
    fulfillment = request.POST.get("fulfillment") or "pickup"
    notes = (request.POST.get("notes") or "").strip()
    address_json = None
    if fulfillment == "delivery":
        address_json = {
            "cep": request.POST.get("cep") or "",
            "logradouro": request.POST.get("logradouro") or "",
            "numero": request.POST.get("numero") or "",
            "complemento": request.POST.get("complemento") or "",
            "bairro": request.POST.get("bairro") or "",
            "cidade": request.POST.get("cidade") or "",
            "uf": request.POST.get("uf") or "",
        }

    if len(name) < 2:
        return JsonResponse({"flash": {"type": "error", "title": "Ops", "message": "Informe um nome válido."}}, status=422)
    try:
        phone = to_e164(phone_raw)
    except Exception:
        return JsonResponse({"flash": {"type": "error", "title": "Telefone inválido", "message": "Informe no formato BR (ex.: +55 11 9XXXX-XXXX)."}}, status=422)

    if not request.session.get("delivery_phone_verified"):
        return JsonResponse({"flash": {"type": "error", "title": "Verificação necessária", "message": "Valide seu telefone por SMS."}}, status=422)

    delivery_fee = 0
    discount = 0
    subtotal = calc["subtotal_cents"]
    total = subtotal + delivery_fee - discount

    order = Order.objects.create(
        card=card,
        code=_gen_order_code(str(card.id)),
        status="pending",
        customer_name=name,
        customer_phone=phone,
        customer_email=email,
        fulfillment=fulfillment,
        address_json=address_json,
        subtotal_cents=subtotal,
        delivery_fee_cents=delivery_fee,
        discount_cents=discount,
        total_cents=total,
        notes=notes,
    )
    # Snapshot items
    for entry in calc["items"]:
        oi = OrderItem.objects.create(
            order=order,
            menu_item=entry["item"],
            qty=entry["qty"],
            base_price_cents_snapshot=entry["unit_price_cents"],
            line_subtotal_cents=entry["line_subtotal_cents"],
            notes="",
        )
        # Persist options/texts
        selections = entry.get("selections") or {}
        for mg in entry["item"].modifier_groups.order_by("order", "created_at").all():
            raw = selections.get(str(mg.id)) or selections.get(mg.id)
            if mg.type == "text":
                if raw:
                    OrderItemText.objects.create(order_item=oi, modifier_group=mg, text_value=str(raw)[:100])
            else:
                # Normalize to list to avoid iterating characters from a string
                if raw is None:
                    iter_ids = []
                elif isinstance(raw, (list, tuple)):
                    iter_ids = list(raw)
                else:
                    iter_ids = [raw]
                for opt_id in iter_ids:
                    opt = get_object_or_404(ModifierOption, pk=opt_id, modifier_group=mg)
                    OrderItemOption.objects.create(order_item=oi, modifier_option=opt, price_delta_cents_snapshot=int(opt.price_delta_cents or 0))

    # Notify card owner via SMS (best effort)
    try:
        if card.notification_phone:
            enqueue(
                type='sms',
                to=card.notification_phone,
                template_code='owner_new_order',
                payload={'code': order.code, 'orders_url': f"{settings.DASHBOARD_BASE_URL}/delivery/cards/{card.id}/orders/page"},
                idempotency_key=f'owner_new_order:{order.id}'
            )
    except Exception:
        #pprint.pprint("Failed to enqueue owner notification:", e)
        pass

    viewer_path = reverse("viewer:order_detail", args=[order.public_code])
    try:
        viewer_url = request.build_absolute_uri(viewer_path)
    except Exception:
        viewer_url = viewer_path
    link_payload = {
        "title": card.title or "Seu pedido",
        "code": order.code,
        "public_code": order.public_code,
        "url": viewer_url,
    }

    # Customer notifications (best effort)
    try:
        if order.customer_phone:
            enqueue(
                type='sms',
                to=order.customer_phone,
                template_code='viewer_order_link',
                payload=link_payload,
                idempotency_key=f'orderlink:sms:{order.id}'
            )
    except Exception:
        pass

    try:
        if order.customer_email:
            enqueue(
                type='email',
                to=order.customer_email,
                template_code='viewer_order_link',
                payload=link_payload,
                idempotency_key=f'orderlink:email:{order.id}'
            )
    except Exception:
        pass

    # Clear cart
    _save_cart(request, str(card.id), {"items": []})

    # TODO: notifications via worker (email/SMS)
    return render(request, "public/checkout_confirm.html", {"card": card, "order": order})


def cep_lookup_public(request, nickname: str):
    card = _ensure_delivery_card(nickname)
    cep = (request.GET.get("cep") or "").strip()
    norm = re.sub(r"\D", "", cep)
    ctx = {"error": None, "logradouro": "", "bairro": "", "cidade": "", "uf": ""}
    if not re.fullmatch(r"\d{8}", norm):
        ctx["error"] = "CEP inválido."
        return render(request, "public/_checkout_addr_fields.html", ctx)
    try:
        with urllib.request.urlopen(f"https://viacep.com.br/ws/{norm}/json/", timeout=4) as resp:
            raw = resp.read()
            jd = json.loads(raw.decode("utf-8"))
        if not jd.get("erro"):
            ctx.update({
                "logradouro": jd.get("logradouro") or "",
                "bairro": jd.get("bairro") or "",
                "cidade": jd.get("localidade") or "",
                "uf": (jd.get("uf") or "").upper(),
            })
        else:
            ctx["error"] = "CEP não encontrado."
    except Exception:
        ctx["error"] = "Falha ao consultar CEP."
    return render(request, "public/_checkout_addr_fields.html", ctx)


@require_http_methods(["POST"])  # send SMS code
def delivery_send_code(request, nickname: str):
    card = _ensure_delivery_card(nickname)
    phone_raw = (request.POST.get("phone") or "").strip()
    try:
        phone = to_e164(phone_raw)
    except Exception as e:
        return render(request, "public/_verify_block_delivery.html", {"error": str(e) or "Telefone inválido"})
    sk = _session_key(request)
    cooldown_key = f"dv:cool:{sk}:{phone}"
    if cache.get(cooldown_key):
        return render(request, "public/_verify_block_delivery.html", {"error": "Aguarde antes de reenviar.", "phone": phone})
    code = gen_code(6)
    try:
        enqueue(
            type='sms',
            to=phone,
            template_code='booking_phone_verify',
            payload={'code': code, 'ttl_min': 5},
            idempotency_key=f'deliveryverify:{sk}:{hash_code(code)}'
        )
    except Exception:
        # Mesmo que o envio falhe, não travar UI com erro interno
        pass
    pv_key = f"dv:data:{sk}:{phone}"
    cache.set(pv_key, {"code": hash_code(code), "attempts": 5}, 300)
    cache.set(cooldown_key, 1, 60)
    request.session["delivery_phone_verified"] = False
    resp = render(request, "public/_verify_block_delivery.html", {"phone": phone, "card": card})
    try:
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "SMS enviado", "message": "Enviamos um código para verificação."}})
    except Exception:
        pass
    return resp


@require_http_methods(["POST"])  # verify SMS code
def delivery_verify_code(request, nickname: str):
    card = _ensure_delivery_card(nickname)
    phone_raw = (request.POST.get("phone") or "").strip()
    code = (request.POST.get("code") or "").strip()
    try:
        phone = to_e164(phone_raw)
    except Exception as e:
        return render(request, "public/_verify_block_delivery.html", {"error": str(e) or "Telefone inválido"})
    sk = _session_key(request)
    pv_key = f"dv:data:{sk}:{phone}"
    data = cache.get(pv_key)
    if not data:
        resp = render(request, "public/_verify_block_delivery.html", {"phone": phone, "card": card, "error": "Código expirado. Reenvie."})
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Código expirado", "message": "Reenvie o SMS."}})
        return resp
    if data.get("attempts", 0) <= 0:
        return render(request, "public/_verify_block_delivery.html", {"phone": phone, "error": "Muitas tentativas. Reenvie."})
    if data.get("code") != hash_code(code):
        data["attempts"] = max(0, int(data.get("attempts", 1)) - 1)
        cache.set(pv_key, data, 300)
        resp = render(request, "public/_verify_block_delivery.html", {"phone": phone, "card": card, "error": "Código incorreto."})
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Código incorreto", "message": "Tente novamente."}})
        return resp
    request.session["delivery_phone_verified"] = True
    resp = render(request, "public/_verify_block_delivery.html", {"phone": phone, "card": card, "verified": True})
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Telefone verificado", "message": "Você já pode concluir o pedido."}})
    return resp
