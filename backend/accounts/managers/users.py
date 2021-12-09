from django.contrib.auth.models import UserManager
from django.db import models
from django.db.models.functions.comparison import Coalesce


class CustomUserManager(UserManager):

    def with_meta(self):
        i = 0
        return self.annotate(
            group_count=Coalesce(models.Count("groups"), 0)
        )
