from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .markdown import render_markdown


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class RenderedMarkdownModel(TimeStampedModel):
    markdown_field = "body_markdown"
    html_field = "body_html"

    class Meta:
        abstract = True

    def clean(self) -> None:
        super().clean()
        raw = getattr(self, self.markdown_field, "")
        try:
            rendered = render_markdown(raw)
        except ValueError as exc:
            raise ValidationError({self.markdown_field: str(exc)}) from exc
        setattr(self, self.html_field, rendered)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            field_set = set(update_fields)
            field_set.add(self.html_field)
            kwargs["update_fields"] = list(field_set)
        super().save(*args, **kwargs)


class NewsPostQuerySet(models.QuerySet):
    def public(self) -> "NewsPostQuerySet":
        now = timezone.now()
        return self.filter(
            is_public=True,
        ).filter(
            models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now),
            models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now),
        )


class NewsPost(RenderedMarkdownModel):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    body_markdown = models.TextField()
    body_html = models.TextField(blank=True)
    is_public = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    order = models.IntegerField(default=0, help_text="Maior valor aparece primeiro.")

    objects = NewsPostQuerySet.as_manager()

    class Meta:
        ordering = ("-order", "-created_at")

    def __str__(self) -> str:
        return self.title

    @property
    def is_active(self) -> bool:
        now = timezone.now()
        if not self.is_public:
            return False
        if self.starts_at and self.starts_at > now:
            return False
        if self.ends_at and self.ends_at < now:
            return False
        return True


class HelperQuerySet(models.QuerySet):
    def public(self) -> "HelperQuerySet":
        return self.filter(is_public=True)


class Helper(RenderedMarkdownModel):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    body_markdown = models.TextField()
    body_html = models.TextField(blank=True)
    is_public = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    objects = HelperQuerySet.as_manager()

    class Meta:
        ordering = ("order", "title")

    def __str__(self) -> str:
        return self.title

class HelperRule(TimeStampedModel):
    helper = models.ForeignKey(Helper, on_delete=models.CASCADE, related_name="rules")
    route_pattern = models.CharField(max_length=255, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("route_pattern", "helper_id")
        verbose_name = "Helper rule"
        verbose_name_plural = "Helper rules"

    def __str__(self) -> str:
        return f"{self.route_pattern} → {self.helper}"
