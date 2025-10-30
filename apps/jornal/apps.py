from django.apps import AppConfig


class JornalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.jornal"
    verbose_name = "Jornal"

    def ready(self) -> None:
        from . import signals  # noqa: F401
