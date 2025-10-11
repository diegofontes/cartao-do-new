import random
import string
import uuid
from dataclasses import dataclass
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from PIL import Image, ImageDraw, ImageFont

from apps.cards.models import Card, CardAddress, LinkButton, SocialLink
from apps.delivery.models import MenuGroup, MenuItem
from apps.scheduling.models import SchedulingService
from apps.search.models import SearchCategory, SearchProfile

User = get_user_model()


FIRST_NAMES = [
    "Ana",
    "Beatriz",
    "Carlos",
    "Diego",
    "Eduarda",
    "Fernanda",
    "Guilherme",
    "Helena",
    "Igor",
    "Juliana",
    "Karina",
    "Lucas",
    "Marina",
    "Natália",
    "Otávio",
    "Paula",
    "Rafael",
    "Sofia",
    "Thiago",
    "Vivian",
]

LAST_NAMES = [
    "Almeida",
    "Barbosa",
    "Campos",
    "Dias",
    "Esteves",
    "Ferraz",
    "Gonçalves",
    "Haddad",
    "Ibrahim",
    "Jardim",
    "Klein",
    "Lopes",
    "Macedo",
    "Novaes",
    "Oliveira",
    "Pereira",
    "Queiroz",
    "Ribeiro",
    "Silva",
    "Teixeira",
]


CITY_PRESETS = [
    {
        "label": "São Paulo - Bela Vista",
        "cep": "01310-930",
        "logradouro": "Avenida Paulista",
        "bairro": "Bela Vista",
        "cidade": "São Paulo",
        "uf": "SP",
        "lat": -23.561684,
        "lng": -46.655981,
    }
    # ,
    # {
    #     "label": "Rio de Janeiro - Botafogo",
    #     "cep": "22250-040",
    #     "logradouro": "Rua Voluntários da Pátria",
    #     "bairro": "Botafogo",
    #     "cidade": "Rio de Janeiro",
    #     "uf": "RJ",
    #     "lat": -22.946102,
    #     "lng": -43.181916,
    # },
    # {
    #     "label": "Belo Horizonte - Savassi",
    #     "cep": "30140-110",
    #     "logradouro": "Rua Pernambuco",
    #     "bairro": "Savassi",
    #     "cidade": "Belo Horizonte",
    #     "uf": "MG",
    #     "lat": -19.933302,
    #     "lng": -43.936356,
    # },
    # {
    #     "label": "Curitiba - Batel",
    #     "cep": "80420-090",
    #     "logradouro": "Avenida Batel",
    #     "bairro": "Batel",
    #     "cidade": "Curitiba",
    #     "uf": "PR",
    #     "lat": -25.440017,
    #     "lng": -49.281558,
    # },
    # {
    #     "label": "Porto Alegre - Moinhos de Vento",
    #     "cep": "90570-051",
    #     "logradouro": "Rua Padre Chagas",
    #     "bairro": "Moinhos de Vento",
    #     "cidade": "Porto Alegre",
    #     "uf": "RS",
    #     "lat": -30.026538,
    #     "lng": -51.199137,
    # },
]


@dataclass
class BusinessTheme:
    key: str
    label: str
    category: SearchCategory
    mode: str
    description: str
    title_templates: list[str]
    services: list[dict] | None = None
    menu: list[dict] | None = None
    socials: list[str] | None = None
    radius_km: float = 12.0


BUSINESS_THEMES: list[BusinessTheme] = [
    BusinessTheme(
        key="salao",
        label="Salão de Cabeleireiro",
        category=SearchCategory.ESTETICA,
        mode="appointment",
        description="Especialistas em coloração, corte e tratamentos capilares personalizados.",
        title_templates=[
            "Studio {first_name} Hair",
            "Salão {last_name} & Cor",
            "Beleza por {name}",
        ],
        services=[
            {"name": "Corte feminino com visagismo", "duration": 60, "type": "local"},
            {"name": "Coloração premium", "duration": 120, "type": "local"},
            {"name": "Escova modelada", "duration": 45, "type": "local"},
        ],
        socials=["instagram", "facebook", "whatsapp", "site"],
        radius_km=8.0,
    ),
    BusinessTheme(
        key="consultoria",
        label="Consultoria Contábil",
        category=SearchCategory.CONSULTORIA,
        mode="appointment",
        description="Planejamento tributário e gestão financeira para pequenas empresas.",
        title_templates=[
            "Contábil {last_name} Consultores",
            "{last_name} & Associados",
            "Escritório Fiscal {first_name}",
        ],
        services=[
            {"name": "Diagnóstico fiscal completo", "duration": 90, "type": "remote"},
            {"name": "Abertura de empresa simplificada", "duration": 60, "type": "remote"},
            {"name": "Consultoria financeira mensal", "duration": 45, "type": "remote"},
        ],
        socials=["linkedin", "site", "whatsapp"],
        radius_km=20.0,
    ),
    BusinessTheme(
        key="advocacia",
        label="Escritório de Advocacia",
        category=SearchCategory.CONSULTORIA,
        mode="appointment",
        description="Equipe especializada em direito empresarial e contratos estratégicos.",
        title_templates=[
            "{last_name} Advocacia Empresarial",
            "Sociedade de Advogados {last_name}",
            "{first_name} Legal Advisors",
        ],
        services=[
            {"name": "Revisão de contratos", "duration": 60, "type": "remote"},
            {"name": "Compliance e LGPD", "duration": 75, "type": "remote"},
            {"name": "Consultoria societária", "duration": 90, "type": "remote"},
        ],
        socials=["linkedin", "site", "instagram"],
        radius_km=25.0,
    ),
    BusinessTheme(
        key="hamburgueria",
        label="Hamburgueria Artesanal",
        category=SearchCategory.DELIVERY,
        mode="delivery",
        description="Blend próprio, molhos autorais e opções vegetarianas com entrega rápida.",
        title_templates=[
            "{first_name} Burger Lab",
            "Casa do Burger {last_name}",
            "Garage Burger {first_name}",
        ],
        menu=[
            {
                "group": "Burgers Clássicos",
                "items": [
                    {"name": "Burger da Casa", "price": 3290, "description": "Blend 160g, queijo prato, molho especial e picles."},
                    {"name": "Cheddar Bacon", "price": 3490, "description": "Cheddar inglês cremoso e bacon caramelizado."},
                    {"name": "Veggie Fresh", "price": 3090, "description": "Burger de grão-de-bico, maionese verde e tomate confit."},
                ],
            },
            {
                "group": "Acompanhamentos",
                "items": [
                    {"name": "Batata rústica", "price": 1490, "description": "Batatas assadas com alecrim e sal de parrilla."},
                    {"name": "Onion Rings", "price": 1590, "description": "Cebolas crocantes com aioli da casa."},
                ],
            },
        ],
        socials=["instagram", "whatsapp", "site", "facebook"],
        radius_km=6.0,
    ),
    BusinessTheme(
        key="pizzaria",
        label="Pizzaria Napolitana",
        category=SearchCategory.DELIVERY,
        mode="delivery",
        description="Massa de fermentação lenta, ingredientes frescos e entregas noturnas.",
        title_templates=[
            "Forneria {last_name}",
            "{first_name} Pizza & Co.",
            "Napoli {last_name}",
        ],
        menu=[
            {
                "group": "Pizzas Salgadas",
                "items": [
                    {"name": "Margherita Verace", "price": 4290, "description": "Molho pelati, mozzarella de búfala e manjericão fresco."},
                    {"name": "Calabresa Artesanal", "price": 4390, "description": "Calabresa curada, cebola roxa e azeitonas pretas."},
                    {"name": "Quatro Queijos", "price": 4590, "description": "Mozzarella, gorgonzola, grana padano e catupiry."},
                ],
            },
            {
                "group": "Doces",
                "items": [
                    {"name": "Nutella com Morango", "price": 3890, "description": "Creme de avelã, morangos frescos e crocante de castanhas."},
                ],
            },
        ],
        socials=["instagram", "whatsapp", "site"],
        radius_km=10.0,
    ),
    BusinessTheme(
        key="oficina",
        label="Oficina Mecânica",
        category=SearchCategory.MANUTENCAO,
        mode="appointment",
        description="Diagnóstico eletrônico, mecânica preventiva e atendimento rápido.",
        title_templates=[
            "AutoCenter {last_name}",
            "{first_name} Motors",
            "Pit Stop {last_name}",
        ],
        services=[
            {"name": "Revisão completa", "duration": 120, "type": "onsite"},
            {"name": "Troca de óleo e filtros", "duration": 45, "type": "onsite"},
            {"name": "Check-up eletrônico", "duration": 60, "type": "onsite"},
        ],
        socials=["facebook", "whatsapp", "site"],
        radius_km=15.0,
    ),
    BusinessTheme(
        key="petwalker",
        label="Passeios para Pets",
        category=SearchCategory.TRANSPORTE,
        mode="appointment",
        description="Passeios personalizados, enriquecimento ambiental e relatórios pós-atividade.",
        title_templates=[
            "{first_name} Pet Walkers",
            "Clube do Pet {last_name}",
            "Passeios & Carinho {first_name}",
        ],
        services=[
            {"name": "Passeio individual (30 min)", "duration": 30, "type": "onsite"},
            {"name": "Passeio em grupo (60 min)", "duration": 60, "type": "onsite"},
            {"name": "Dog sitter personalizado", "duration": 90, "type": "onsite"},
        ],
        socials=["instagram", "facebook", "whatsapp"],
        radius_km=7.5,
    ),
]


AVATAR_COLORS = [
    "#EC7063",
    "#AF7AC5",
    "#5DADE2",
    "#48C9B0",
    "#F4D03F",
    "#EB984E",
    "#95A5A6",
]


class Command(BaseCommand):
    help = "Gera usuários, cartões e dados associados para testar a busca local."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=5, help="Quantidade de cartões fake a gerar")
        parser.add_argument(
            "--mode",
            choices=["mixed", "appointment", "delivery"],
            default="mixed",
            help="Restringe o modo do cartão a agendamentos, delivery ou mistura",
        )
        parser.add_argument(
            "--password",
            default="Senha123!",
            help="Senha padrão aplicada aos usuários gerados",
        )

    def handle(self, *args, **options):
        count = options["count"]
        mode = options["mode"]
        password = options["password"]

        themes = self._filter_themes(mode)
        if not themes:
            self.stdout.write(self.style.ERROR("Nenhum tema disponível para o modo solicitado."))
            return

        created_cards: list[Card] = []
        for _ in range(count):
            theme = random.choice(themes)
            with transaction.atomic():
                full_name = self._random_full_name()
                user = self._create_user(full_name, password)
                card = self._create_card(user, full_name, theme)
                self._create_address(card)
                self._create_social_links(card, theme)
                self._create_link_button(card)
                if theme.mode == "appointment":
                    self._create_services(card, theme)
                elif theme.mode == "delivery":
                    self._create_menu(card, theme)
                self._create_search_profile(card, theme)
                card.publish()
                created_cards.append(card)
                self.stdout.write(self.style.SUCCESS(f"Card publicado: {card.title} · usuário {user.email}"))

        self.stdout.write("")
        self.stdout.write("Resumo:")
        for card in created_cards:
            profile = getattr(card, "search_profile", None)
            coords = "sem coordenadas"
            if profile and profile.origin:
                coords = f"lat {profile.origin.y:.4f}, lng {profile.origin.x:.4f}"
            self.stdout.write(
                f" - {card.title} ({card.mode}) → categoria {card.search_profile.category if card.search_profile else 'n/a'} → {coords}"
            )
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Usuários criados com senha padrão informada."))

    def _filter_themes(self, mode: str) -> list[BusinessTheme]:
        if mode == "mixed":
            return BUSINESS_THEMES
        return [theme for theme in BUSINESS_THEMES if theme.mode == mode]

    def _random_full_name(self) -> str:
        return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

    def _create_user(self, full_name: str, password: str) -> User:
        first, last = full_name.split(" ", 1)
        username = slugify(f"{first}-{last}-{uuid.uuid4().hex[:6]}")
        email_slug = slugify(full_name)
        email = f"{email_slug}.{uuid.uuid4().hex[:4]}@example.com"
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first,
            last_name=last,
        )
        return user

    def _create_card(self, user: User, full_name: str, theme: BusinessTheme) -> Card:
        first, last = full_name.split(" ", 1)
        template = random.choice(theme.title_templates)
        title = template.format(name=full_name, first_name=first, last_name=last)
        slug_base = slugify(title)[:80]
        slug = f"{slug_base}-{uuid.uuid4().hex[:6]}"
        card = Card.objects.create(
            owner=user,
            title=title,
            description=theme.description,
            slug=slug,
            mode=theme.mode,
            status="draft",
            nickname=None,
            notification_phone=self._random_phone(),
        )
        initials = self._initials_from_name(full_name)
        self._assign_avatar(card, initials)
        return card

    def _initials_from_name(self, name: str) -> str:
        parts = name.split()
        initials = "".join(part[0].upper() for part in parts[:2])
        return initials or "XP"

    def _assign_avatar(self, card: Card, initials: str) -> None:
        color = random.choice(AVATAR_COLORS)
        sizes = {"avatar": 512, "avatar_w128": 128, "avatar_w64": 64}
        for field_name, size in sizes.items():
            image = Image.new("RGB", (size, size), color)
            draw = ImageDraw.Draw(image)
            font = self._load_font(int(size * 0.45))
            if hasattr(draw, "textbbox"):
                text_bbox = draw.textbbox((0, 0), initials, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
            else:  # Pillow < 8 compatibility
                text_width, text_height = draw.textsize(initials, font=font)
            position = ((size - text_width) / 2, (size - text_height) / 2)
            draw.text(position, initials, fill="white", font=font)
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            buffer.seek(0)
            filename = f"{card.slug}_{size}.jpg"
            getattr(card, field_name).save(filename, ContentFile(buffer.read()), save=True)

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        try:
            return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
        except OSError:
            return ImageFont.load_default()

    def _random_phone(self) -> str:
        digits = "9" + "".join(random.choices(string.digits, k=8))
        area_code = random.choice(["11", "21", "31", "41", "51"])
        return f"+55{area_code}{digits}"

    def _create_address(self, card: Card) -> None:
        city = random.choice(CITY_PRESETS)
        CardAddress.objects.create(
            card=card,
            label="Matriz",
            cep=city["cep"],
            logradouro=city["logradouro"],
            numero=str(random.randint(10, 999)),
            complemento=f"Sala {random.randint(1, 10)}",
            bairro=city["bairro"],
            cidade=city["cidade"],
            uf=city["uf"],
            lat=city["lat"],
            lng=city["lng"],
        )

    def _create_social_links(self, card: Card, theme: BusinessTheme) -> None:
        socials = theme.socials or []
        if not socials:
            return
        slug = slugify(card.title)
        whatsapp_digits = card.notification_phone.replace("+", "").replace(" ", "")
        for order, platform in enumerate(socials):
            url = self._social_url(platform, slug, whatsapp_digits)
            label = platform.capitalize()
            SocialLink.objects.create(
                card=card,
                platform=platform,
                label=label,
                url=url,
                order=order,
            )

    def _social_url(self, platform: str, slug: str, whatsapp_digits: str) -> str:
        if platform == "instagram":
            return f"https://www.instagram.com/{slug}/"
        if platform == "facebook":
            return f"https://www.facebook.com/{slug}/"
        if platform == "linkedin":
            return f"https://www.linkedin.com/company/{slug}/"
        if platform == "whatsapp":
            return f"https://wa.me/{whatsapp_digits}"
        if platform == "tiktok":
            return f"https://www.tiktok.com/@{slug}"
        if platform == "youtube":
            return f"https://www.youtube.com/@{slug}"
        if platform == "github":
            return f"https://github.com/{slug}"
        if platform == "site":
            return f"https://{slug}.com.br"
        return f"https://{slug}.example.com"

    def _create_link_button(self, card: Card) -> None:
        phone_digits = card.notification_phone.replace("+", "").replace(" ", "")
        label = "Agende pelo WhatsApp" if card.mode == "appointment" else "Peça pelo WhatsApp"
        LinkButton.objects.create(
            card=card,
            label=label,
            url=f"https://wa.me/{phone_digits}",
            icon="whatsapp",
            order=0,
        )

    def _create_services(self, card: Card, theme: BusinessTheme) -> None:
        services = theme.services or []
        timezone = "America/Sao_Paulo"
        for order, data in enumerate(services):
            SchedulingService.objects.create(
                card=card,
                name=data["name"],
                description=f"{theme.description} Serviço #{order + 1}",
                timezone=timezone,
                duration_minutes=data.get("duration", 60),
                type=data.get("type", "remote"),
            )

    def _create_menu(self, card: Card, theme: BusinessTheme) -> None:
        menu_groups = theme.menu or []
        for order, group_data in enumerate(menu_groups):
            group = MenuGroup.objects.create(
                card=card,
                name=group_data["group"],
                order=order,
            )
            for item in group_data["items"]:
                MenuItem.objects.create(
                    card=card,
                    group=group,
                    name=item["name"],
                    description=item.get("description", theme.description),
                    base_price_cents=item["price"],
                    is_active=True,
                    kitchen_time_min=item.get("kitchen_time_min"),
                )

    def _create_search_profile(self, card: Card, theme: BusinessTheme) -> None:
        city = random.choice(CITY_PRESETS)
        origin = Point(city["lng"], city["lat"], srid=4326)
        SearchProfile.objects.update_or_create(
            card=card,
            defaults={
                "category": theme.category,
                "origin": origin,
                "radius_km": theme.radius_km,
                "active": True,
            },
        )
