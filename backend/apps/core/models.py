from django.db import models


class CreatedAtModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class TimeStampedModel(CreatedAtModel):
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
