from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("accounts/", include("apps.accounts.urls")),
]
