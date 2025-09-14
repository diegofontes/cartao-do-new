from django.apps import AppConfig


class CardsConfig(AppConfig):
    name = "apps.cards"

    def ready(self):
        # Import signals
        from . import signals  # noqa: F401

