import mimetypes
from django.http import FileResponse, Http404, HttpResponse
from django.core.files.storage import default_storage
from django.shortcuts import get_object_or_404
from django.utils.http import http_date
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from apps.cards.models import Card, GalleryItem


def image_public(request, path: str):
    # Only allow files under our upload prefix
    if not path.startswith("u/"):
        raise Http404
    if not default_storage.exists(path):
        raise Http404
    f = default_storage.open(path, "rb")
    ctype, _ = mimetypes.guess_type(path)
    resp = FileResponse(f, content_type=ctype or "application/octet-stream")
    resp["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


@login_required
def card_avatar_private(request, id, size: str):
    card = get_object_or_404(Card, id=id)
    if card.owner != request.user and card.status != "published":
        return HttpResponse(status=403)
    if size == "w64" and card.avatar_w64:
        path = card.avatar_w64.name
    elif size == "w128" and card.avatar_w128:
        path = card.avatar_w128.name
    else:
        path = card.avatar.name if card.avatar else None
    if not path or not default_storage.exists(path):
        raise Http404
    f = default_storage.open(path, "rb")
    ctype, _ = mimetypes.guess_type(path)
    resp = FileResponse(f, content_type=ctype or "application/octet-stream")
    resp["Cache-Control"] = "private, no-store"
    return resp


@login_required
def gallery_private(request, id, size: str):
    item = get_object_or_404(GalleryItem, id=id)
    card = item.card
    if card.owner != request.user and card.status != "published":
        return HttpResponse(status=403)
    if size == "w256" and item.thumb_w256:
        path = item.thumb_w256.name
    elif size == "w768" and item.thumb_w768:
        path = item.thumb_w768.name
    else:
        path = item.file.name
    if not path or not default_storage.exists(path):
        raise Http404
    f = default_storage.open(path, "rb")
    ctype, _ = mimetypes.guess_type(path)
    resp = FileResponse(f, content_type=ctype or "application/octet-stream")
    resp["Cache-Control"] = "private, no-store"
    return resp

