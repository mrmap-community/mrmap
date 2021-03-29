from django.conf import settings
from django.test import TestCase

from guardian_roles.models.core import TemplateRole, OwnerBasedRole
from guardian_roles.utils import get_owner_model


class OwnerDeletionTestCase(TestCase):
    """Test on_delete configuration of all related objects for the `settings.GUARDIAN_ROLES_OWNER_MODEL` model."""
    def setUp(self) -> None:
        TemplateRole.objects.create(name=settings.GUARDIAN_ROLES_ADMIN_ROLE_FOR_ROLE_ADMIN_ROLE)
        TemplateRole.objects.create(name='some_other_role')
        self.owner = get_owner_model().objects.create(organization_name='owner-1')

    def test_owner_deletion(self) -> None:
        """
        Test on_delete configuration for all related objects for the `settings.GUARDIAN_ROLES_OWNER_MODEL` model.

        * If a instance of `settings.GUARDIAN_ROLES_OWNER_MODEL` is deleted, all related `OwnerBasedRole` shall
          also be deleted.
        """
        self.owner.delete()
        self.assertFalse(OwnerBasedRole.objects.exists())

        # todo: relevant ObjectBasedRole instances shall not containing users from the OwnerBasedRole
        #  if they are not member of other OwnerBasedRole instances which grants the same permissions?
        self.assertTrue(False)


class ContentObjectDeletionTestCase(TestCase):
    """Test on_delete configuration of all related objects for the `ObjectBasedRole` model."""
    def setUp(self) -> None:
        TemplateRole.objects.create(name=settings.GUARDIAN_ROLES_ADMIN_ROLE_FOR_ROLE_ADMIN_ROLE)
        TemplateRole.objects.create(name='some_other_role')
        self.owner = get_owner_model().objects.create(organization_name='owner-1')

    def test_related_content_object_deletion(self) -> None:
        """
        Test on_delete configuration for all related objects for the `settings.GUARDIAN_ROLES_OWNER_MODEL` model.

        * If a the related content_object is deleted, the `ObjectBasedRole` it self shall also deleted.
        """
        # todo
        self.assertTrue(False)

