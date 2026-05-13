from django.db import migrations


DEFAULT_PLANS = [
    {
        "slug": "free",
        "name": "Grátis",
        "price": "0.00",
        "max_accounts": 2,
        "has_investments": False,
        "has_goals": False,
        "has_advanced_reports": False,
        "has_personalized_guidance": False,
        "has_priority_support": False,
    },
    {
        "slug": "essencial",
        "name": "Essencial",
        "price": "19.90",
        "max_accounts": None,
        "has_investments": False,
        "has_goals": False,
        "has_advanced_reports": False,
        "has_personalized_guidance": False,
        "has_priority_support": False,
    },
    {
        "slug": "pro",
        "name": "Pro",
        "price": "34.90",
        "max_accounts": None,
        "has_investments": True,
        "has_goals": True,
        "has_advanced_reports": True,
        "has_personalized_guidance": True,
        "has_priority_support": True,
    },
]


def populate_plans(apps, schema_editor):
    Plan = apps.get_model("subscriptions", "Plan")
    for data in DEFAULT_PLANS:
        Plan.objects.get_or_create(slug=data["slug"], defaults=data)


def remove_default_plans(apps, schema_editor):
    Plan = apps.get_model("subscriptions", "Plan")
    Plan.objects.filter(slug__in=["free", "essencial", "pro"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("subscriptions", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(populate_plans, remove_default_plans),
    ]
