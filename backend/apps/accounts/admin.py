from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User
    ordering = ("username",)
    list_display = ("username", "display_name", "email", "is_staff", "is_active")
    search_fields = ("username", "display_name", "email")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Profile", {"fields": ("display_name", "email")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at", "last_login")
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "display_name", "email", "password1", "password2", "is_staff", "is_active"),
            },
        ),
    )
