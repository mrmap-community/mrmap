"""
Core models to implement the possibility of ACLs
"""
from uuid import uuid4
from django.contrib.auth.models import Group
from django.db import models
from django.utils.translation import gettext_lazy as _
from MrMap.icons import get_icon, IconEnum
from acl.managers import AclManager
from main.models import CommonInfo, GenericModelMixin


class AccessControlList(GenericModelMixin, Group, CommonInfo):
    """
    Access control list model to store group based lists of users with sets of permissions and objects which shall
    be accessible.
    """
    objects = AclManager()
    uuid = models.UUIDField(primary_key=True,
                            default=uuid4,
                            editable=False)
    description = models.CharField(max_length=256,
                                   null=True,
                                   blank=True,
                                   verbose_name=_('Description'),
                                   help_text=_('Describe what this acl shall allow.'))
    # todo
    """
    accessible_metadata = models.ManyToManyField(to='service.Metadata',
                                                 blank=True,
                                                 verbose_name=_('Accessible resource'),
                                                 help_text=_('Select which resource shall be accessible with the configured permissions.'))
    """
    # todo
    """accessible_pendingtasks = models.ManyToManyField(to='structure.PendingTask',
                                                     blank=True,
                                                     verbose_name=_('Accessible pending tasks'),
                                                     help_text=_('Select which pending tasks shall be accessible with the configured permissions.'))
     """
    accessible_accesscontrollists = models.ManyToManyField(to='self',
                                                           blank=True,
                                                           verbose_name=_('Accessible access control lists'),
                                                           help_text=_('Select which acl\'s shall be accessible with the configured permissions.'))
    accessible_organizations = models.ManyToManyField(to='structure.Organization',
                                                      blank=True,
                                                      verbose_name=_('Accessible organizations'),
                                                      help_text=_('Select which organizations shall be accessible with the configured permissions.'))

    default_acl = models.BooleanField(default=False,
                                      editable=False)

    organization_admin = models.BooleanField(default=False,
                                             editable=False)

    class Meta:
        verbose_name = _('Access Control List')
        verbose_name_plural = _('Access Control Lists')

    @classmethod
    def get_accessible_fields(cls):
        """helper function to get all m2m fields where the name contains 'accessible_'"""
        return [field for field in cls._meta.local_many_to_many if 'accessible_' in field.name]

    @classmethod
    def get_ownable_models(cls):
        """helper function to get all model classes which could be linked by a acl"""
        return [field.related_model for field in cls.get_accessible_fields()]

    @classmethod
    def get_accessible_field_by_related_model(cls, model):
        """helper function to get one specific accessible field by given related_model"""
        return next(field for field in cls.get_accessible_fields() if field.related_model == model)

    def get_add_function_by_field(self, field):
        """helper function to get a custom add function for a m2m field if it exists"""
        try:
            func = getattr(self, f'add_{field.name}')
        except AttributeError:
            field = getattr(self, f'{field.name}')
            func = field.add
        return func
