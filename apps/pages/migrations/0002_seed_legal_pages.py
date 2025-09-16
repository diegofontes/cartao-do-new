from django.db import migrations


def seed_pages(apps, schema_editor):
    LegalPage = apps.get_model('pages', 'LegalPage')
    defaults = {
        'is_active': True,
    }
    LegalPage.objects.update_or_create(
        slug='politica_de_privacidade',
        defaults={**defaults, 'title': 'Política de Privacidade', 'content': 'Sua privacidade é importante. Descreva aqui sua política.'}
    )
    LegalPage.objects.update_or_create(
        slug='termos_de_uso',
        defaults={**defaults, 'title': 'Termos de Uso', 'content': 'Estes são os termos de uso do serviço.'}
    )


def unseed_pages(apps, schema_editor):
    LegalPage = apps.get_model('pages', 'LegalPage')
    LegalPage.objects.filter(slug__in=['politica_de_privacidade', 'termos_de_uso']).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('pages', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_pages, unseed_pages),
    ]

