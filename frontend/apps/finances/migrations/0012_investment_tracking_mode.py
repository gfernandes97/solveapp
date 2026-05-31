from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finances", "0011_userachievement_levels"),
    ]

    operations = [
        migrations.AddField(
            model_name="investment",
            name="tracking_mode",
            field=models.CharField(
                choices=[("fin", "Financeiro"), ("qp", "Qtd × Preço")],
                default="fin",
                max_length=3,
            ),
        ),
    ]
