# Generated manually to bootstrap GeoDjango search profiles
from __future__ import annotations

import uuid

import django.contrib.gis.db.models.fields
import django.core.validators
from django.contrib.postgres.indexes import GistIndex
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("cards", "0011_card_notification_phone"),
    ]

    operations = [
        migrations.CreateModel(
            name="SearchProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("estetica_beleza", "Estética e Beleza"),
                            ("manutencao", "Manutenção"),
                            ("transporte", "Transporte"),
                            ("delivery", "Delivery"),
                            ("consultoria", "Consultoria (contábil/advogado)"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "origin",
                    django.contrib.gis.db.models.fields.PointField(blank=True, null=True, srid=4326),
                ),
                (
                    "radius_km",
                    models.FloatField(validators=[django.core.validators.MinValueValidator(0.01)]),
                ),
                ("active", models.BooleanField(default=True)),
                (
                    "card",
                    models.OneToOneField(
                        on_delete=models.CASCADE,
                        related_name="search_profile",
                        to="cards.card",
                    ),
                ),
            ],
            options={
                "indexes": [
                    GistIndex(fields=["origin"], name="search_origin_gix"),
                    models.Index(fields=["active"], name="search_active_idx"),
                ],
            },
        ),
    ]
