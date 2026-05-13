from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    # aliases de URL compatíveis com templates existentes (login, register, logout)
    path("accounts/", include("apps.accounts.urls")),
    # allauth: social auth (Google), password reset, email confirmation, etc.
    path("accounts/", include("allauth.urls")),
]
