from django.contrib.gis.db import models as gis_models
from django.contrib.postgres.indexes import GistIndex
from django.core.validators import MinValueValidator
from django.db import models

from apps.common.models import BaseModel


class SearchCategory(models.TextChoices):
    ESTETICA = "estetica_beleza", "Estética e Beleza"
    MANUTENCAO = "manutencao", "Manutenção"
    TRANSPORTE = "transporte", "Transporte"
    DELIVERY = "delivery", "Delivery"
    CONSULTORIA = "consultoria", "Consultoria (contábil/advogado)"


class SearchProfile(BaseModel):
    card = models.OneToOneField(
        "cards.Card",
        on_delete=models.CASCADE,
        related_name="search_profile",
    )
    category = models.CharField(max_length=32, choices=SearchCategory.choices)
    origin = gis_models.PointField(srid=4326, null=True, blank=True)
    radius_km = models.FloatField(validators=[MinValueValidator(0.01)])
    active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            GistIndex(fields=["origin"], name="search_origin_gix"),
            models.Index(fields=["active"], name="search_active_idx"),
        ]

    def __str__(self) -> str:
        return f"Perfil de busca · {self.card.title}"

    @property
    def has_coordinates(self) -> bool:
        return self.origin is not None
