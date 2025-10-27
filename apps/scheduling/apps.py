from django.apps import AppConfig


class SchedulingConfig(AppConfig):
    name = "apps.scheduling"
    verbose_name = "Agendamentos"

    def ready(self):
        from . import signals  # noqa: F401
