import imghdr
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


def validate_max_size(file, max_bytes: int):
    size = getattr(file, "size", 0) or 0
    if size > max_bytes:
        raise ValidationError("Arquivo excede 2MB.")


def validate_mime_and_magic(file, allowed: set[str]):
    mime = getattr(file, "content_type", "") or ""
    if mime not in allowed:
        raise ValidationError("Tipo de arquivo não permitido.")
    # Magic bytes (quick sniff)
    pos = file.tell()
    head = file.read(512)
    file.seek(pos)
    kind = imghdr.what(None, head)
    if kind not in {"jpeg", "png"}:
        raise ValidationError("Conteúdo de imagem inválido.")


def verify_image(file):
    pos = file.tell()
    try:
        img = Image.open(file)
        img.verify()
    except (UnidentifiedImageError, OSError):
        raise ValidationError("Imagem corrompida ou inválida.")
    finally:
        file.seek(pos)


def validate_upload(file):
    from django.conf import settings
    validate_max_size(file, getattr(settings, "MAX_UPLOAD_BYTES", 2 * 1024 * 1024))
    validate_mime_and_magic(file, getattr(settings, "ALLOWED_IMAGE_MIME_TYPES", {"image/jpeg", "image/png"}))
    verify_image(file)

