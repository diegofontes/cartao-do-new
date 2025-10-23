from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cards", "0012_galleryitem_importance_galleryitem_service_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="card",
            name="about_markdown",
            field=models.TextField(blank=True, default="", null=True),
        ),
    ]

