from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_merge_20250924_1816"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="birth_date",
            field=models.DateField(null=True, blank=True),
        ),
        migrations.RemoveField(
            model_name="user",
            name="age",
        ),
    ]

