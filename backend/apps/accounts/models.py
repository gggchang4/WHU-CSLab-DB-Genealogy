from django.db import models

from apps.core.models import TimeStampedModel


class User(TimeStampedModel):
    user_id = models.BigAutoField(primary_key=True)
    username = models.CharField(max_length=64, unique=True)
    password_hash = models.CharField(max_length=255)
    display_name = models.CharField(max_length=128)
    email = models.EmailField(max_length=255, unique=True)

    class Meta:
        db_table = "users"
        ordering = ["username"]

    def __str__(self) -> str:
        return self.display_name or self.username
