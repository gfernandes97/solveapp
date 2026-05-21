from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finances', '0007_recurringtransaction_goal'),
    ]

    operations = [
        migrations.AddField(
            model_name='transaction',
            name='is_transfer',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='transaction',
            name='transfer_ref',
            field=models.CharField(blank=True, db_index=True, max_length=36),
        ),
    ]
