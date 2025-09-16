from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cards", "0007_card_tabs_order"),
    ]

    operations = [
        migrations.AlterField(
            model_name="card",
            name="avatar",
            field=models.ImageField(
                upload_to="uploads/cards/avatars/", max_length=255, blank=True, null=True
            ),
        ),
        migrations.AlterField(
            model_name="card",
            name="avatar_w64",
            field=models.ImageField(
                upload_to="uploads/cards/avatars/", max_length=255, blank=True, null=True
            ),
        ),
        migrations.AlterField(
            model_name="card",
            name="avatar_w128",
            field=models.ImageField(
                upload_to="uploads/cards/avatars/", max_length=255, blank=True, null=True
            ),
        ),
        migrations.AlterField(
            model_name="galleryitem",
            name="file",
            field=models.FileField(upload_to="cards/gallery/", max_length=255),
        ),
        migrations.AlterField(
            model_name="galleryitem",
            name="thumb_w256",
            field=models.FileField(
                upload_to="cards/gallery/", max_length=255, blank=True, null=True
            ),
        ),
        migrations.AlterField(
            model_name="galleryitem",
            name="thumb_w768",
            field=models.FileField(
                upload_to="cards/gallery/", max_length=255, blank=True, null=True
            ),
        ),
    ]

