from django.urls import path

from allauth.account.views import LoginView, LogoutView, SignupView

# Aliases de URL para compatibilidade com templates existentes.
urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("register/", SignupView.as_view(), name="register"),
    path("logout/", LogoutView.as_view(), name="logout"),
]
