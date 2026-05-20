from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finances", "0005_transaction_goal"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountMonthSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("month", models.DateField()),
                ("balance", models.DecimalField(decimal_places=2, max_digits=12)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="monthly_snapshots",
                        to="finances.account",
                    ),
                ),
            ],
            options={
                "verbose_name": "Saldo Mensal",
                "verbose_name_plural": "Saldos Mensais",
                "ordering": ["-month"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="accountmonthsnapshot",
            unique_together={("account", "month")},
        ),
    ]
