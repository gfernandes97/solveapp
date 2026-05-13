from django.urls import path
from . import views

urlpatterns = [
    path("", views.overview, name="dashboard"),
    path("transactions/", views.transactions, name="transactions"),
    path("investments/", views.investments, name="investments"),
    path("goals/", views.goals, name="goals"),
    path("settings/", views.settings, name="settings"),
]
