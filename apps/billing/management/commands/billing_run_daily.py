import datetime as dt
from django.core.management.base import BaseCommand
from apps.billing.daily import billing_run_daily


class Command(BaseCommand):
    help = "Executa rotina diária de faturamento por âncora do usuário (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument("--date", dest="date", help="Data UTC (YYYY-MM-DD) para processar; default: hoje", default=None)

    def handle(self, *args, **options):
        d = options.get("date")
        if d:
            try:
                process_date = dt.date.fromisoformat(d)
            except ValueError:
                return self.stdout.write(self.style.ERROR("--date inválida; use YYYY-MM-DD"))
        else:
            process_date = None
        res = billing_run_daily(process_date)
        self.stdout.write(self.style.SUCCESS(f"OK: {res}"))

