from __future__ import annotations

from django.db.models.signals import post_delete, post_save

from . import selectors
from .models import Helper, HelperRule, NewsPost


def _invalidate_news(*_args, **_kwargs) -> None:
    selectors.invalidate_news_cache()


def _invalidate_helpers(*_args, **_kwargs) -> None:
    selectors.invalidate_helper_cache()


post_save.connect(_invalidate_news, sender=NewsPost, dispatch_uid="jornal.news.invalidate.save")
post_delete.connect(_invalidate_news, sender=NewsPost, dispatch_uid="jornal.news.invalidate.delete")
post_save.connect(_invalidate_helpers, sender=Helper, dispatch_uid="jornal.helper.invalidate.save")
post_delete.connect(_invalidate_helpers, sender=Helper, dispatch_uid="jornal.helper.invalidate.delete")
post_save.connect(_invalidate_helpers, sender=HelperRule, dispatch_uid="jornal.helper_rule.invalidate.save")
post_delete.connect(_invalidate_helpers, sender=HelperRule, dispatch_uid="jornal.helper_rule.invalidate.delete")

