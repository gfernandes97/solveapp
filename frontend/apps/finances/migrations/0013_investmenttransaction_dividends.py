from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finances", "0012_investment_tracking_mode"),
    ]

    operations = [
        migrations.AlterField(
            model_name="investmenttransaction",
            name="type",
            field=models.CharField(
                choices=[
                    ("buy", "Compra"),
                    ("sell", "Venda"),
                    ("earnings", "Rendimento"),
                    ("dividends", "Dividendo"),
                ],
                max_length=10,
            ),
        ),
    ]
