from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.db.models.functions import Lower
from apps.common.models import BaseModel


class Card(BaseModel):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("ready", "Ready"),
        ("published", "Published"),
        ("archived", "Archived"),
    ]
    MODE_CHOICES = [
        ("appointment", "Appointment"),
        ("delivery", "Delivery"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cards")
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    # Processed avatar files (original JPEG + thumbs)
    avatar = models.ImageField(upload_to="uploads/cards/avatars/", max_length=255, blank=True, null=True)
    avatar_w64 = models.ImageField(upload_to="uploads/cards/avatars/", max_length=255, blank=True, null=True)
    avatar_w128 = models.ImageField(upload_to="uploads/cards/avatars/", max_length=255, blank=True, null=True)
    avatar_hash = models.CharField(max_length=64, blank=True, null=True)
    avatar_rev = models.PositiveIntegerField(default=0)
    slug = models.SlugField(max_length=120)
    nickname = models.CharField(max_length=32, blank=True, null=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    # Mode determines viewer/admin features: appointment scheduling or delivery menu
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default="appointment")
    published_at = models.DateTimeField(blank=True, null=True)
    # Deactivation/archival lifecycle
    deactivation_marked = models.BooleanField(default=False)
    deactivation_marked_at = models.DateTimeField(blank=True, null=True)
    archived_at = models.DateTimeField(blank=True, null=True)
    archived_reason = models.TextField(blank=True, null=True)
    nickname_locked_until = models.DateTimeField(blank=True, null=True)
    # Comma-separated order for public tabs (links,gallery,services)
    tabs_order = models.CharField(max_length=64, default="links,gallery,services")
    # Número para notificações (telefone E.164 opcional)
    notification_phone = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "slug"], name="uniq_card_slug_per_owner"),
            models.UniqueConstraint(Lower("nickname"), name="uniq_card_nickname_lower", condition=~models.Q(nickname=None)),
        ]
        indexes = [
            models.Index(fields=["owner", "status"]),
        ]

    def can_publish(self) -> bool:
        if not self.title or len(self.title.strip()) < 3:
            return False
        if not self.avatar:
            return False
        has_link = self.linkbutton_set.exists()
        has_address = self.addresses.exists()
        return has_link or has_address

    def publish(self):
        if not self.can_publish():
            raise ValueError("Card does not meet publish requirements")
        self.status = "published"
        self.published_at = timezone.now()
        self.save(update_fields=["status", "published_at"])

    @property
    def is_delivery(self) -> bool:
        return self.mode == "delivery"


class CardAddress(BaseModel):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=80)
    # Endereço (BR)
    cep = models.CharField(max_length=9, help_text="CEP no formato 00000-000")
    logradouro = models.CharField(max_length=200, blank=True)
    numero = models.CharField(max_length=20, blank=True)
    complemento = models.CharField(max_length=100, blank=True)
    bairro = models.CharField(max_length=80, blank=True)
    cidade = models.CharField(max_length=80, blank=True)
    uf = models.CharField(max_length=2, blank=True)
    pais = models.CharField(max_length=2, default="BR")
    lat = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)

    class Meta:
        indexes = [models.Index(fields=["card"]) ]


PLATFORM_CHOICES = [
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("linkedin", "LinkedIn"),
    ("whatsapp", "WhatsApp"),
    ("x", "X"),
    ("tiktok", "TikTok"),
    ("youtube", "YouTube"),
    ("github", "GitHub"),
    ("site", "Site"),
]


class SocialLink(BaseModel):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="social_links")
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    label = models.CharField(max_length=80, blank=True)
    url = models.URLField()
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["card", "order"])]


class LinkButton(BaseModel):
    card = models.ForeignKey(Card, on_delete=models.CASCADE)
    label = models.CharField(max_length=80)
    url = models.URLField()
    icon = models.CharField(max_length=40, blank=True)
    order = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        indexes = [models.Index(fields=["card", "order"])]


class GalleryItem(BaseModel):
    card = models.ForeignKey(Card, on_delete=models.CASCADE)
    file = models.FileField(upload_to="cards/gallery/", max_length=255)
    thumb_w256 = models.FileField(upload_to="cards/gallery/", max_length=255, blank=True, null=True)
    thumb_w768 = models.FileField(upload_to="cards/gallery/", max_length=255, blank=True, null=True)
    caption = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        indexes = [models.Index(fields=["card", "order"])]
