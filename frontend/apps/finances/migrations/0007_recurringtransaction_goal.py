from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('finances', '0006_accountmonthsnapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='recurringtransaction',
            name='goal',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='recurring_contributions',
                to='finances.goal',
            ),
        ),
    ]
