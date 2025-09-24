from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_auth_extensions"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="age",
            field=models.PositiveSmallIntegerField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="user",
            name="gender",
            field=models.CharField(
                max_length=1,
                null=True,
                blank=True,
                choices=[
                    ("M", "Masculino"),
                    ("F", "Feminino"),
                    ("O", "Outro"),
                    ("N", "Prefiro não informar"),
                ],
            ),
        ),
    ]

