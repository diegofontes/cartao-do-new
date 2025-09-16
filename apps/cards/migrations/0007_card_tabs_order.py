from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cards', '0006_remove_card_uniq_card_nickname_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='card',
            name='tabs_order',
            field=models.CharField(default='links,gallery,services', max_length=64),
        ),
    ]

