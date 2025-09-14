from django.core.management.base import BaseCommand
from apps.billing.tasks import close_monthly_billing

class Command(BaseCommand):
    help = "Fecha o ciclo mensal (mês anterior) e gera faturas no Stripe."

    def add_arguments(self, parser):
        parser.add_argument("--for", dest="run_for", help="Periodo base AAAA-MM (opcional)", default=None)

    def handle(self, *args, **options):
        result = close_monthly_billing.delay(options.get("run_for")).get(timeout=60)
        self.stdout.write(self.style.SUCCESS(f"OK: {result}"))
