from django.urls import path

from allauth.account.views import LoginView, LogoutView, SignupView

# Aliases de URL para manter compatibilidade com os templates existentes.
# 'login', 'register', 'logout' são usados em todo o projeto;
# allauth usa 'account_login', 'account_signup', 'account_logout'.
urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("register/", SignupView.as_view(), name="register"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
