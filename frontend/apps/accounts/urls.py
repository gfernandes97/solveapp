from django.urls import path

from allauth.account.views import LoginView, LogoutView, SignupView

from . import views

# Aliases de URL para compatibilidade com templates existentes.
urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("register/", SignupView.as_view(), name="register"),
    path("logout/", LogoutView.as_view(), name="logout"),
    # LGPD
    path("exportar-dados/", views.data_export, name="data_export"),
    path("excluir-conta/", views.delete_account_request, name="delete_account_request"),
    path("cancelar-exclusao/", views.cancel_deletion_request, name="cancel_deletion_request"),
]
