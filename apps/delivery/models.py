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
    TYPE_CHOICES = [("single", "Single"), ("multi", "Multi"), ("text", "Text")]

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
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("preparing", "Preparing"),
        ("ready", "Ready"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]
    FULFILLMENT_CHOICES = [("delivery", "Delivery"), ("pickup", "Pickup")]

    card = models.ForeignKey("cards.Card", on_delete=models.CASCADE, related_name="orders")
    code = models.CharField(max_length=12, db_index=True)
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

