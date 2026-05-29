from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finances", "0010_investmenttransaction"),
    ]

    operations = [
        migrations.AddField(
            model_name="userachievement",
            name="level",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="userachievement",
            name="best_level",
            field=models.PositiveSmallIntegerField(default=1),
        ),
    ]
