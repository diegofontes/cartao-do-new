from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("cards", "0010_card_mode"),
    ]

    operations = [
        migrations.CreateModel(
            name="MenuGroup",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField(max_length=120)),
                ("order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("card", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="menu_groups", to="cards.card")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["card", "order"], name="delivery_men_card_id_f2f1d4_idx"),
                ],
                "unique_together": {("card", "slug")},
            },
        ),
        migrations.CreateModel(
            name="MenuItem",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("slug", models.SlugField(max_length=160)),
                ("description", models.TextField(blank=True)),
                ("image", models.ImageField(blank=True, max_length=255, null=True, upload_to="uploads/menu/items/")),
                ("base_price_cents", models.IntegerField()),
                ("is_active", models.BooleanField(default=True)),
                ("kitchen_time_min", models.PositiveIntegerField(blank=True, null=True)),
                ("sku", models.CharField(blank=True, max_length=60)),
                ("card", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="menu_items", to="cards.card")),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="delivery.menugroup")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["card", "group", "is_active"], name="delivery_men_card_id_f6a0b1_idx"),
                ],
                "unique_together": {("group", "slug")},
            },
        ),
        migrations.CreateModel(
            name="ModifierGroup",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("type", models.CharField(choices=[("single", "Single"), ("multi", "Multi"), ("text", "Text")], max_length=10)),
                ("min_choices", models.PositiveIntegerField(default=0)),
                ("max_choices", models.PositiveIntegerField(blank=True, null=True)),
                ("required", models.BooleanField(default=False)),
                ("order", models.PositiveIntegerField(default=0)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="modifier_groups", to="delivery.menuitem")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["item", "order"], name="delivery_mod_item_id_1a2bd6_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ModifierOption",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("label", models.CharField(max_length=120)),
                ("price_delta_cents", models.IntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("order", models.PositiveIntegerField(default=0)),
                ("modifier_group", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="options", to="delivery.modifiergroup")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["modifier_group", "order"], name="delivery_mod_modifie_14b99a_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(db_index=True, max_length=12)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("accepted", "Accepted"), ("rejected", "Rejected"), ("preparing", "Preparing"), ("ready", "Ready"), ("completed", "Completed"), ("cancelled", "Cancelled")], default="pending", max_length=20)),
                ("customer_name", models.CharField(max_length=160)),
                ("customer_phone", models.CharField(max_length=40)),
                ("customer_email", models.EmailField(blank=True, max_length=254)),
                ("fulfillment", models.CharField(choices=[("delivery", "Delivery"), ("pickup", "Pickup")], default="pickup", max_length=10)),
                ("address_json", models.JSONField(blank=True, null=True)),
                ("subtotal_cents", models.IntegerField()),
                ("delivery_fee_cents", models.IntegerField(default=0)),
                ("discount_cents", models.IntegerField(default=0)),
                ("total_cents", models.IntegerField()),
                ("notes", models.TextField(blank=True)),
                ("card", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="orders", to="cards.card")),
            ],
            options={
                "indexes": [
                    models.Index(fields=["card", "status", "created_at"], name="delivery_ord_card_id_5d3517_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("qty", models.PositiveIntegerField(default=1)),
                ("base_price_cents_snapshot", models.IntegerField()),
                ("line_subtotal_cents", models.IntegerField()),
                ("notes", models.CharField(blank=True, max_length=200)),
                ("menu_item", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to="delivery.menuitem")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="delivery.order")),
            ],
        ),
        migrations.CreateModel(
            name="OrderItemOption",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("price_delta_cents_snapshot", models.IntegerField(default=0)),
                ("modifier_option", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to="delivery.modifieroption")),
                ("order_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="options", to="delivery.orderitem")),
            ],
        ),
        migrations.CreateModel(
            name="OrderItemText",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("text_value", models.CharField(max_length=100)),
                ("modifier_group", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to="delivery.modifiergroup")),
                ("order_item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="texts", to="delivery.orderitem")),
            ],
        ),
    ]

