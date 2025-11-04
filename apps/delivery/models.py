from django.db import models
from django.core.validators import MinValueValidator
from django.utils.text import slugify
from apps.common.models import BaseModel


class MenuGroup(BaseModel):
    card = models.ForeignKey("cards.Card", on_delete=models.CASCADE, related_name="menu_groups")
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120)
    order = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["card", "order"]) ]
        unique_together = ("card", "slug")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:120]
        super().save(*args, **kwargs)


class MenuItem(BaseModel):
    card = models.ForeignKey("cards.Card", on_delete=models.CASCADE, related_name="menu_items")
    group = models.ForeignKey(MenuGroup, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=160)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="uploads/menu/items/", max_length=255, blank=True, null=True)
    base_price_cents = models.IntegerField(validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    kitchen_time_min = models.PositiveIntegerField(blank=True, null=True)
    sku = models.CharField(max_length=60, blank=True)

    class Meta:
        indexes = [models.Index(fields=["card", "group", "is_active"]) ]
        unique_together = ("group", "slug")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:160]
        super().save(*args, **kwargs)


class ModifierGroup(BaseModel):
    TYPE_CHOICES = [("single", "Única"), ("multi", "Múltipla"), ("text", "Texto")]

    item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name="modifier_groups")
    name = models.CharField(max_length=120)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    min_choices = models.PositiveIntegerField(default=0)
    max_choices = models.PositiveIntegerField(blank=True, null=True)
    required = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        indexes = [models.Index(fields=["item", "order"]) ]


class ModifierOption(BaseModel):
    modifier_group = models.ForeignKey(ModifierGroup, on_delete=models.CASCADE, related_name="options")
    label = models.CharField(max_length=120)
    price_delta_cents = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])

    class Meta:
        indexes = [models.Index(fields=["modifier_group", "order"]) ]


class Order(BaseModel):
    STATUS_CHOICES = [
        ("pending", "Pendente"),
        ("accepted", "Aceito"),
        ("rejected", "Recusado"),
        ("preparing", "Preparando"),
        ("ready", "Pronto"),
        ("shipped", "Enviado"),
        ("completed", "Concluído"),
        ("cancelled", "Cancelado"),
    ]
    FULFILLMENT_CHOICES = [("delivery", "Entrega"), ("pickup", "Retirada")]

    card = models.ForeignKey("cards.Card", on_delete=models.CASCADE, related_name="orders")
    code = models.CharField(max_length=12, db_index=True)
    public_code = models.CharField(max_length=12, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    customer_name = models.CharField(max_length=160)
    customer_phone = models.CharField(max_length=40)
    customer_email = models.EmailField(blank=True)
    fulfillment = models.CharField(max_length=10, choices=FULFILLMENT_CHOICES, default="pickup")
    address_json = models.JSONField(blank=True, null=True)
    subtotal_cents = models.IntegerField(validators=[MinValueValidator(0)])
    delivery_fee_cents = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    discount_cents = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    total_cents = models.IntegerField(validators=[MinValueValidator(0)])
    notes = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["card", "status", "created_at"]) ]

    def save(self, *args, **kwargs):
        from apps.common.codes import generate_unique_code

        is_new = self._state.adding
        prev_status = None
        should_track_status = True
        source = getattr(self, "_status_change_source", None)
        note = getattr(self, "_status_change_note", "")
        if not is_new and self.pk:
            update_fields = kwargs.get("update_fields")
            should_track_status = update_fields is None or "status" in update_fields
            if should_track_status:
                prev_status = (
                    type(self)
                    .objects.filter(pk=self.pk)
                    .values_list("status", flat=True)
                    .first()
                )

        if not self.public_code:
            def _exists(code: str) -> bool:
                qs = type(self).objects.filter(public_code=f"D{code}")
                if self.pk:
                    qs = qs.exclude(pk=self.pk)
                return qs.exists()

            base_code = generate_unique_code(length=7, exists=_exists)
            self.public_code = f"D{base_code}"
        super().save(*args, **kwargs)
        if hasattr(self, "_status_change_source"):
            delattr(self, "_status_change_source")
        if hasattr(self, "_status_change_note"):
            delattr(self, "_status_change_note")
        if is_new:
            OrderStatusChange.objects.create(
                order=self,
                status=self.status,
                source=source or "initial",
                note=note or "",
            )
        elif should_track_status and prev_status != self.status:
            OrderStatusChange.objects.create(
                order=self,
                status=self.status,
                source=source or "",
                note=note or "",
            )

    def set_status(self, status: str, *, source: str | None = None, note: str = "") -> None:
        self.status = status
        if source:
            self._status_change_source = source
        if note:
            self._status_change_note = note
        self.save(update_fields=["status"])


class OrderItem(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.SET_NULL, null=True)
    qty = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    base_price_cents_snapshot = models.IntegerField(validators=[MinValueValidator(0)])
    line_subtotal_cents = models.IntegerField(validators=[MinValueValidator(0)])
    notes = models.CharField(max_length=200, blank=True)


class OrderItemOption(BaseModel):
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="options")
    modifier_option = models.ForeignKey(ModifierOption, on_delete=models.SET_NULL, null=True)
    price_delta_cents_snapshot = models.IntegerField(default=0)


class OrderItemText(BaseModel):
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="texts")
    modifier_group = models.ForeignKey(ModifierGroup, on_delete=models.SET_NULL, null=True)
    text_value = models.CharField(max_length=100)


class OrderStatusChange(BaseModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_changes")
    status = models.CharField(max_length=20, choices=Order.STATUS_CHOICES)
    source = models.CharField(max_length=32, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["order", "created_at"], name="delivery_ord_idx"),
        ]
        ordering = ["created_at"]
