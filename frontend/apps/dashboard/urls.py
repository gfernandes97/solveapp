from django.urls import path
from . import views

urlpatterns = [
    # Overview
    path("", views.overview, name="dashboard"),

    # Diagnóstico
    path("diagnostico/", views.diagnostico, name="diagnostico"),

    # Investimentos
    path("investimentos/", views.investimentos, name="investimentos"),

    # Lançamentos (transações)
    path("lancamentos/", views.lancamentos, name="lancamentos"),
    path("lancamentos/<int:pk>/editar/", views.lancamento_editar, name="lancamento_editar"),
    path("lancamentos/<int:pk>/excluir/", views.lancamento_excluir, name="lancamento_excluir"),

    # Transferências entre custódias
    path("transferencias/criar/", views.transferencia_criar, name="transferencia_criar"),

    # Lançamentos fixos (recorrentes)
    path("fixos/criar/", views.fixo_criar, name="fixo_criar"),
    path("fixos/<int:pk>/editar/", views.fixo_editar, name="fixo_editar"),
    path("fixos/<int:pk>/excluir/", views.fixo_excluir, name="fixo_excluir"),

    # Projeção
    path("projecao/", views.projecao, name="projecao"),

    # Contas
    path("contas/", views.contas, name="contas"),
    path("contas/<int:pk>/editar/", views.conta_editar, name="conta_editar"),
    path("contas/<int:pk>/excluir/", views.conta_excluir, name="conta_excluir"),
    path("contas/snapshot/", views.snapshot_criar, name="snapshot_criar"),
    path("contas/snapshot/ajax/", views.snapshot_ajax, name="snapshot_ajax"),
    path("contas/snapshot/<int:pk>/excluir/", views.snapshot_excluir, name="snapshot_excluir"),

    # Metas
    path("metas/", views.metas, name="metas"),
    path("metas/<int:pk>/editar/", views.meta_editar, name="meta_editar"),
    path("metas/<int:pk>/excluir/", views.meta_excluir, name="meta_excluir"),

    # Investimentos
    path("investimentos/criar/", views.investimento_criar, name="investimento_criar"),
    path("investimentos/boleta/", views.investimento_boleta, name="investimento_boleta"),
    path("investimentos/boleta/<int:pk>/editar/", views.investimento_boleta_editar, name="investimento_boleta_editar"),
    path("investimentos/<int:pk>/editar/", views.investimento_editar, name="investimento_editar"),
    path("investimentos/<int:pk>/excluir/", views.investimento_excluir, name="investimento_excluir"),
    path("investimentos/<int:pk>/rendimento/", views.investimento_rendimento, name="investimento_rendimento"),

    # Categorias
    path("categorias/criar/", views.categoria_criar, name="categoria_criar"),
    path("categorias/<int:pk>/editar/", views.categoria_editar, name="categoria_editar"),
    path("categorias/<int:pk>/excluir/", views.categoria_excluir, name="categoria_excluir"),

    # Configurações
    path("settings/", views.settings, name="settings"),
    path("settings/update/", views.settings_update, name="settings_update"),

    # Sol tour
    path("sol/mark-shown/", views.sol_mark_shown, name="sol_mark_shown"),
]
