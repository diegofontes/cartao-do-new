from django.db import models
from apps.common.models import BaseModel


class LegalPage(BaseModel):
    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=120)
    content = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=["slug"])]

    def __str__(self) -> str:
        return self.title

