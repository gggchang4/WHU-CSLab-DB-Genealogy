from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.accounts.managers import UserManager


class User(TimeStampedModel, AbstractBaseUser, PermissionsMixin):
    user_id = models.BigAutoField(primary_key=True)
    username = models.CharField(max_length=64, unique=True)
    display_name = models.CharField(max_length=128)
    email = models.EmailField(max_length=255, unique=True)
    password = models.CharField(_("password"), max_length=128, db_column="password_hash")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email", "display_name"]

    class Meta:
        db_table = "users"
        ordering = ["username"]

    def __str__(self) -> str:
        return self.display_name or self.username
