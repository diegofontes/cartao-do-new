import os
from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Agenda: todo dia 1 às 00:05 executa fechamento do mês anterior
from celery.schedules import crontab
app.conf.beat_schedule = {
    "close-monthly-billing": {
        "task": "apps.billing.tasks.close_monthly_billing",
        "schedule": crontab(minute=5, hour=0, day_of_month="1"),
    },
    "run-daily-billing": {
        "task": "apps.billing.tasks.run_daily_billing",
        # Run daily at 03:00 server time
        "schedule": crontab(minute=0, hour=3),
    },
}
