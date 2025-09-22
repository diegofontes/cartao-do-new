import json
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST
from django.conf import settings
from apps.common.validators import validate_upload

from apps.cards.models import Card
from .models import MenuGroup, MenuItem, ModifierGroup, ModifierOption, Order


def _check_card(request, card_id: str) -> Card:
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    if getattr(card, "deactivation_marked", False):
        raise PermissionError("Card marked for deactivation")
    if card.mode != "delivery":
        raise PermissionError("Card is not in delivery mode")
    return card


@login_required
def menu_partial(request, card_id):
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    groups = MenuGroup.objects.filter(card=card).order_by("order", "created_at")
    # counts for limits
    limits = getattr(settings, "DELIVERY_LIMITS", {})
    return render(request, "delivery/_menu_admin.html", {"card": card, "groups": groups, "limits": limits})


@login_required
@require_POST
def add_group(request, card_id):
    try:
        card = _check_card(request, card_id)
    except PermissionError as e:
        return HttpResponseForbidden(str(e))
    name = (request.POST.get("name") or "").strip()
    if not name:
        return HttpResponseBadRequest("name required")
    # Limit
    max_groups = int(getattr(settings, "DELIVERY_LIMITS", {}).get("groups_per_card", 20))
    if MenuGroup.objects.filter(card=card).count() >= max_groups:
        resp = menu_partial(request, card_id)
        resp.status_code = 422
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Limite", "message": "Máximo de grupos atingido."}})
        return resp
    order = (MenuGroup.objects.filter(card=card).order_by("-order").first().order + 1) if MenuGroup.objects.filter(card=card).exists() else 0
    MenuGroup.objects.create(card=card, name=name, order=order)
    resp = menu_partial(request, card_id)
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Feito!", "message": "Grupo adicionado."}})
    return resp


@login_required
@require_POST
def add_item(request, card_id):
    try:
        card = _check_card(request, card_id)
    except PermissionError as e:
        return HttpResponseForbidden(str(e))
    group_id = request.POST.get("group_id")
    group = get_object_or_404(MenuGroup, id=group_id, card=card)
    name = (request.POST.get("name") or "").strip()
    base_price_cents = int(request.POST.get("base_price_cents") or 0)
    if len(name) < 2 or base_price_cents < 0:
        return HttpResponseBadRequest("invalid fields")
    # Optional image upload
    img = request.FILES.get("image")
    if img is not None:
        max_bytes = getattr(settings, "MAX_UPLOAD_BYTES", 2 * 1024 * 1024)
        if getattr(img, "size", 0) > max_bytes:
            resp = menu_partial(request, card_id)
            resp.status_code = 413
            resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Upload bloqueado", "message": "Imagem excede 2MB."}})
            return resp
        try:
            validate_upload(img)
        except Exception as e:
            resp = menu_partial(request, card_id)
            resp.status_code = 422
            resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Upload inválido", "message": str(e)}})
            return resp
    # Limit
    max_items = int(getattr(settings, "DELIVERY_LIMITS", {}).get("items_per_card", 200))
    if MenuItem.objects.filter(card=card).count() >= max_items:
        resp = menu_partial(request, card_id)
        resp.status_code = 422
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Limite", "message": "Máximo de itens atingido."}})
        return resp
    MenuItem.objects.create(card=card, group=group, name=name, base_price_cents=base_price_cents, slug="", image=img)
    resp = menu_partial(request, card_id)
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Feito!", "message": "Item adicionado."}})
    return resp


@login_required
@require_POST
def delete_item(request, item_id):
    item = get_object_or_404(MenuItem, id=item_id, card__owner=request.user)
    if getattr(item.card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    card = item.card
    item.delete()
    return render(request, "delivery/_menu_admin.html", {"card": card, "groups": MenuGroup.objects.filter(card=card).order_by("order", "created_at")})


@login_required
@require_POST
def add_modifier_group(request, card_id):
    try:
        card = _check_card(request, card_id)
    except PermissionError as e:
        return HttpResponseForbidden(str(e))
    item_id = request.POST.get("item_id")
    item = get_object_or_404(MenuItem, id=item_id, card=card)
    name = (request.POST.get("name") or "").strip()
    type_ = request.POST.get("type")
    min_choices = int(request.POST.get("min_choices") or 0)
    max_choices_raw = request.POST.get("max_choices")
    max_choices = int(max_choices_raw) if (max_choices_raw or "").strip() else None
    required = (request.POST.get("required") == "on") or (request.POST.get("required") == "true")
    # Limit
    max_mg = int(getattr(settings, "DELIVERY_LIMITS", {}).get("modifier_groups_per_item", 20))
    if item.modifier_groups.count() >= max_mg:
        resp = menu_partial(request, card_id)
        resp.status_code = 422
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Limite", "message": "Máximo de grupos de opções atingido."}})
        return resp
    ModifierGroup.objects.create(item=item, name=name, type=type_, min_choices=min_choices, max_choices=max_choices, required=required)
    resp = menu_partial(request, card_id)
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Feito!", "message": "Grupo de opções adicionado."}})
    return resp


@login_required
@require_POST
def delete_group(request, group_id):
    grp = get_object_or_404(MenuGroup, id=group_id, card__owner=request.user)
    if getattr(grp.card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    card = grp.card
    grp.delete()
    return render(request, "delivery/_menu_admin.html", {"card": card, "groups": MenuGroup.objects.filter(card=card).order_by("order", "created_at")})


@login_required
@require_POST
def delete_modifier_group(request, modifier_group_id):
    mg = get_object_or_404(ModifierGroup, id=modifier_group_id, item__card__owner=request.user)
    card = mg.item.card
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    mg.delete()
    return render(request, "delivery/_menu_admin.html", {"card": card, "groups": MenuGroup.objects.filter(card=card).order_by("order", "created_at")})


@login_required
@require_POST
def delete_modifier_option(request, option_id):
    opt = get_object_or_404(ModifierOption, id=option_id, modifier_group__item__card__owner=request.user)
    card = opt.modifier_group.item.card
    if getattr(card, "deactivation_marked", False):
        return HttpResponseForbidden("Card marked for deactivation")
    opt.delete()
    return render(request, "delivery/_menu_admin.html", {"card": card, "groups": MenuGroup.objects.filter(card=card).order_by("order", "created_at")})


@login_required
@require_POST
def add_modifier_option(request, card_id):
    try:
        card = _check_card(request, card_id)
    except PermissionError as e:
        return HttpResponseForbidden(str(e))
    mg_id = request.POST.get("modifier_group_id")
    mg = get_object_or_404(ModifierGroup, id=mg_id, item__card=card)
    label = (request.POST.get("label") or "").strip()
    price_delta_cents = int(request.POST.get("price_delta_cents") or 0)
    # Limit
    max_opts = int(getattr(settings, "DELIVERY_LIMITS", {}).get("options_per_modifier_group", 50))
    if mg.options.count() >= max_opts:
        resp = menu_partial(request, card_id)
        resp.status_code = 422
        resp["HX-Trigger"] = json.dumps({"flash": {"type": "error", "title": "Limite", "message": "Máximo de opções atingido."}})
        return resp
    ModifierOption.objects.create(modifier_group=mg, label=label, price_delta_cents=price_delta_cents)
    resp = menu_partial(request, card_id)
    resp["HX-Trigger"] = json.dumps({"flash": {"type": "success", "title": "Feito!", "message": "Opção adicionada."}})
    return resp


@login_required
def orders_partial(request, card_id):
    card = get_object_or_404(Card, id=card_id, owner=request.user)
    orders = Order.objects.filter(card=card).order_by("-created_at")[:100]
    return render(request, "delivery/_orders_admin.html", {"card": card, "orders": orders})


@login_required
@require_POST
def update_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id, card__owner=request.user)
    status = request.POST.get("status")
    if status not in {"pending","accepted","rejected","preparing","ready","completed","cancelled"}:
        return HttpResponseBadRequest("invalid status")
    order.status = status
    order.save(update_fields=["status"])
    return orders_partial(request, order.card_id)
