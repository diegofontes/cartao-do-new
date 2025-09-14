import io
import hashlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import Literal
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def content_hash(img: Image.Image) -> str:
    bio = io.BytesIO()
    # Save as PNG in memory to hash pixels (avoid EXIF affecting hash)
    ImageOps.exif_transpose(img).convert("RGB").save(bio, format="PNG")
    return hashlib.sha1(bio.getvalue()).hexdigest()


def sanitize(img: Image.Image) -> Image.Image:
    # Remove metadata/EXIF and normalize orientation
    return ImageOps.exif_transpose(img).convert("RGB")


def save_jpeg(img: Image.Image, path: str, quality: int = 82) -> str:
    bio = io.BytesIO()
    img.save(bio, format="JPEG", optimize=True, progressive=True, quality=quality)
    bio.seek(0)
    default_storage.save(path, ContentFile(bio.read()))
    return path


def cover_square(img: Image.Image, size: int) -> Image.Image:
    # Center-crop to square, then resize
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    cropped = img.crop((left, top, left + side, top + side))
    return cropped.resize((size, size), Image.Resampling.LANCZOS)


def contain(img: Image.Image, max_w: int) -> Image.Image:
    w, h = img.size
    if w <= max_w:
        return img.copy()
    ratio = max_w / float(w)
    nh = int(h * ratio)
    return img.resize((max_w, nh), Image.Resampling.LANCZOS)


def build_upload_base(user_id: int, scope: Literal["avatar", "gallery"], now: datetime | None = None) -> str:
    now = now or datetime.utcnow()
    y, m, d = now.strftime("%Y %m %d").split()
    return f"u/{user_id}/{y}/{m}/{d}/{scope}"


def process_avatar(user_id: int, file_obj, now: datetime | None = None) -> dict:
    img = Image.open(file_obj)
    img = sanitize(img)
    h = content_hash(img)
    base = build_upload_base(user_id, "avatar", now)
    orig = save_jpeg(img, f"{base}/avatar-{h}.jpg")
    w64 = save_jpeg(cover_square(img, 64), f"{base}/avatar-{h}-w64.jpg")
    w128 = save_jpeg(cover_square(img, 128), f"{base}/avatar-{h}-w128.jpg")
    return {"orig": orig, "w64": w64, "w128": w128, "hash": h}


def process_gallery(user_id: int, file_obj, now: datetime | None = None) -> dict:
    img = Image.open(file_obj)
    img = sanitize(img)
    h = content_hash(img)
    base = build_upload_base(user_id, "gallery", now)
    orig = save_jpeg(img, f"{base}/img-{h}.jpg")
    w256 = save_jpeg(contain(img, 256), f"{base}/img-{h}-w256.jpg")
    w768 = save_jpeg(contain(img, 768), f"{base}/img-{h}-w768.jpg")
    return {"orig": orig, "w256": w256, "w768": w768, "hash": h}

