from django.contrib.auth import get_user_model
from django.db.models.base import Model
from django.db.models.fields import CharField
from django.db.models.fields.related import ManyToManyField
from django.utils.translation import gettext_lazy as _


class ResourceGroup(Model):
    pass


class Role(Model):
    """Abstract Role model"""
    name = CharField(
        max_length=256,
        verbose_name=_("name"),
        help_text=_("insert a verbose role name")
    )
    users = ManyToManyField(
        to=get_user_model(),
        blank=True,
        verbose_name=_("members"),
        help_text=_("set of users which are member of this role")
    )

    class Meta:
        abstract = True
