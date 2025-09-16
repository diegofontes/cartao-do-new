import datetime as dt
from django.core.management.base import BaseCommand
from apps.billing.daily import billing_run_for_user


class Command(BaseCommand):
    help = "Executa faturamento diário para um único usuário (--user) e mês/dia baseado na âncora."

    def add_arguments(self, parser):
        parser.add_argument("--user", dest="user", type=int, required=True, help="ID do usuário")
        parser.add_argument("--date", dest="date", help="Data UTC (YYYY-MM-DD) para processar; default: hoje", default=None)

    def handle(self, *args, **options):
        uid = options["user"]
        d = options.get("date")
        process_date = None
        if d:
            try:
                process_date = dt.date.fromisoformat(d)
            except ValueError:
                return self.stdout.write(self.style.ERROR("--date inválida; use YYYY-MM-DD"))
        res = billing_run_for_user(uid, process_date)
        if res.get("ok"):
            self.stdout.write(self.style.SUCCESS(f"OK: {res}"))
        else:
            self.stdout.write(self.style.WARNING(f"Skip: {res}"))

