from django.conf import settings


def test_ibge_names_and_companies_are_reserved():
    assert "maria" in settings.RESERVED_NICKNAMES
    assert "google" in settings.RESERVED_NICKNAMES
