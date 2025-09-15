from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = "apps.notifications"
    verbose_name = "Notifications"

    def ready(self):
        # Place for signals, if needed later
        return

