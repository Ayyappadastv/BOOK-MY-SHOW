from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    phone = models.CharField(max_length=15, blank=True)
    is_admin_user = models.BooleanField(default=False)

    def __str__(self):
        return self.username
