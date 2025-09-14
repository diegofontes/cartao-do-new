from django.core.management.base import BaseCommand
from django.urls import get_resolver, URLPattern, URLResolver


class Command(BaseCommand):
    help = "Lista rotas HTML candidatas para ajuste responsivo (nome e padrão)."

    def add_arguments(self, parser):
        parser.add_argument("--namespace", default=None, help="Filtrar por namespace (opcional)")

    def handle(self, *args, **opts):
        ns = opts.get("namespace")
        resolver = get_resolver()

        def walk(urlconf, prefix=""):
            for entry in urlconf.url_patterns:
                if isinstance(entry, URLResolver):
                    if ns and entry.namespace and ns != entry.namespace:
                        # se um namespace foi pedido e este não bate, pula o subresolver
                        continue
                    yield from walk(entry, prefix)
                elif isinstance(entry, URLPattern):
                    name = entry.name or ""
                    # ignora endpoints típicos de API e webhooks
                    if any(seg in (name or "") for seg in ("api", "webhook")):
                        continue
                    pattern = str(entry.pattern)
                    yield (name, pattern)

        rows = sorted({(name, pattern) for name, pattern in walk(resolver)})
        for name, pattern in rows:
            self.stdout.write(f"{name or '-'}\t{pattern}")

