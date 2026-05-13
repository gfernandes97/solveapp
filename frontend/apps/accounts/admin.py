from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "onboarding_step", "onboarding_completed", "phone", "created_at")
    list_filter = ("onboarding_completed", "onboarding_step")
    search_fields = ("user__email",)
    raw_id_fields = ("user",)
