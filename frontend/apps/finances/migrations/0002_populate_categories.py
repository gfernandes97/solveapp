from django.db import migrations


DEFAULT_CATEGORIES = [
    # Receitas
    {"name": "Salário", "type": "income", "icon": "briefcase", "color": "#00C97A"},
    {"name": "Freelance", "type": "income", "icon": "code", "color": "#00C97A"},
    {"name": "Investimentos", "type": "income", "icon": "trending-up", "color": "#00C97A"},
    {"name": "Outros rendimentos", "type": "income", "icon": "plus-circle", "color": "#00C97A"},
    # Despesas — Moradia
    {"name": "Aluguel", "type": "expense", "icon": "home", "color": "#64748B"},
    {"name": "Condomínio", "type": "expense", "icon": "building", "color": "#64748B"},
    {"name": "Contas de casa", "type": "expense", "icon": "zap", "color": "#64748B"},
    {"name": "Mercado", "type": "expense", "icon": "shopping-cart", "color": "#64748B"},
    # Despesas — Transporte
    {"name": "Transporte público", "type": "expense", "icon": "bus", "color": "#64748B"},
    {"name": "Combustível", "type": "expense", "icon": "droplet", "color": "#64748B"},
    {"name": "Uber / 99", "type": "expense", "icon": "car", "color": "#64748B"},
    # Despesas — Saúde
    {"name": "Plano de saúde", "type": "expense", "icon": "heart", "color": "#64748B"},
    {"name": "Farmácia", "type": "expense", "icon": "activity", "color": "#64748B"},
    {"name": "Consultas", "type": "expense", "icon": "user-check", "color": "#64748B"},
    # Despesas — Lazer
    {"name": "Restaurantes", "type": "expense", "icon": "coffee", "color": "#64748B"},
    {"name": "Streaming", "type": "expense", "icon": "tv", "color": "#64748B"},
    {"name": "Lazer e entretenimento", "type": "expense", "icon": "smile", "color": "#64748B"},
    # Despesas — Educação
    {"name": "Educação", "type": "expense", "icon": "book", "color": "#64748B"},
    # Despesas — Financeiras
    {"name": "Cartão de crédito", "type": "expense", "icon": "credit-card", "color": "#64748B"},
    {"name": "Empréstimo", "type": "expense", "icon": "dollar-sign", "color": "#64748B"},
    {"name": "Outras despesas", "type": "expense", "icon": "more-horizontal", "color": "#64748B"},
    # Transferências
    {"name": "Transferência entre contas", "type": "transfer", "icon": "repeat", "color": "#64748B"},
]


def populate_categories(apps, schema_editor):
    Category = apps.get_model("finances", "Category")
    for data in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(
            name=data["name"],
            type=data["type"],
            user=None,
            defaults={**data, "is_default": True},
        )


def remove_default_categories(apps, schema_editor):
    Category = apps.get_model("finances", "Category")
    Category.objects.filter(user=None, is_default=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("finances", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(populate_categories, remove_default_categories),
    ]
