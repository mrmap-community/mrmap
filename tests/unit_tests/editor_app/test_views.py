"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 27.04.20

"""
from django.test import TestCase, Client
from django.urls import reverse

from editor.forms import MetadataEditorForm
from editor.tables import WmsServiceTable, WfsServiceTable, DatasetTable
from service.models import Metadata, MetadataRelation
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service, create_wfs_service
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD

EDITOR_INDEX_NAME = 'editor:index'
EDITOR_WMS_INDEX_NAME = 'editor:wms-index'
EDITOR_WFS_INDEX_NAME = 'editor:wfs-index'

EDITOR_METADATA_EDITOR_NAME = 'editor:edit'
EDITOR_ACCESS_EDITOR_NAME = 'editor:edit_access'
EDITOR_ACCESS_GEOMETRY_EDITOR_NAME = 'editor:access_geometry_form'

EDITOR_DATASET_INDEX_NAME = 'editor:datasets-index'
EDITOR_DATASET_WIZARD_NEW = 'editor:dataset-metadata-wizard-new'
EDITOR_DATASET_WIZARD_EDIT = 'editor:dataset-metadata-wizard-instance'
EDITOR_REMOVE_DATASET = 'editor:remove-dataset-metadata'


class EditorIndexViewTestCase(TestCase):
    """ Test case for basic index view of WMS and WFS editor

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.get_groups().first(), how_much_services=10)
        create_wfs_service(group=self.user.get_groups().first(), how_much_services=10)

    def test_get_index_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        response = self.client.get(
            reverse(EDITOR_INDEX_NAME, ),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/editor_service_table_index.html")
        self.assertIsInstance(response.context["wms_table"], WmsServiceTable)
        self.assertEqual(len(response.context["wms_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["wms_table"].page.object_list), 5)

        self.assertIsInstance(response.context["wfs_table"], WfsServiceTable)
        self.assertEqual(len(response.context["wfs_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["wfs_table"].page.object_list), 5)


class EditorWMSIndexViewTestCase(TestCase):
    """ Test case for basic index view of WMS editor

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.get_groups().first(), how_much_services=10)

    def test_get_index_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        response = self.client.get(
            reverse(EDITOR_WMS_INDEX_NAME, ),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/editor_service_table_index_wms.html")
        self.assertIsInstance(response.context["wms_table"], WmsServiceTable)
        self.assertEqual(len(response.context["wms_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["wms_table"].page.object_list), 5)


class EditorWFSIndexViewTestCase(TestCase):
    """ Test case for basic index view of WFS editor

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wfs_service(group=self.user.get_groups().first(), how_much_services=10)

    def test_get_index_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        response = self.client.get(
            reverse(EDITOR_WFS_INDEX_NAME, ),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/editor_service_table_index_wfs.html")
        self.assertIsInstance(response.context["wfs_table"], WfsServiceTable)
        self.assertEqual(len(response.context["wfs_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["wfs_table"].page.object_list), 5)


class EditorMetadataEditViewTestCase(TestCase):
    """ Test case for basic metadata editor view

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.get_groups().first(), how_much_services=1)

    def test_get_form_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        metadata = Metadata.objects.all().first()
        response = self.client.get(
            reverse(EDITOR_METADATA_EDITOR_NAME, args=(metadata.id,)),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/editor_metadata_index.html")
        self.assertIsInstance(response.context["form"], MetadataEditorForm)


class EditorAccessEditViewTestCase(TestCase):
    """ Test case for basic access editor view

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.get_groups().first(), how_much_services=10)

    def test_get_form_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        metadata = Metadata.objects.all().first()
        response = self.client.get(
            reverse(EDITOR_ACCESS_EDITOR_NAME, args=(metadata.id,)),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/editor_edit_access_index.html")
        self.assertEqual(response.context["service_metadata"], metadata)
        # No form to test

    def test_get_access_geometry_form_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        metadata = Metadata.objects.all().first()
        response = self.client.get(
            reverse(EDITOR_ACCESS_GEOMETRY_EDITOR_NAME, args=(metadata.id,)),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/access_geometry_form.html")
        # No form to test


class EditorDatasetIndexViewTestCase(TestCase):
    """ Test case for basic index view of WMS editor

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.get_groups().first(), how_much_services=10)

    def test_get_index_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        response = self.client.get(
            reverse(EDITOR_DATASET_INDEX_NAME, ),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/editor_service_table_index_datasets.html")
        self.assertIsInstance(response.context["dataset_table"], DatasetTable)
        self.assertEqual(len(response.context["dataset_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["dataset_table"].page.object_list), 5)


class EditorDatasetWizardNewViewTestCase(TestCase):
    """ Test case for basic index view of WMS editor

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.get_groups().first(), how_much_services=10)

    def test_get_wizard_new_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        response = self.client.get(
            reverse(EDITOR_DATASET_WIZARD_NEW, args=('editor:datasets-index', )),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/editor_service_table_index_datasets.html")
        self.assertIsInstance(response.context["dataset_table"], DatasetTable)
        self.assertEqual(len(response.context["dataset_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["dataset_table"].page.object_list), 5)


class EditorDatasetWizardInstanceViewTestCase(TestCase):
    """ Test case for basic index view of WMS editor

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_services = create_wms_service(group=self.user.get_groups().first(), how_much_services=10)

    def test_get_wizard_instance_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        datasets = self.user.get_datasets_as_qs()

        response = self.client.get(
            reverse(EDITOR_DATASET_WIZARD_EDIT, args=('editor:datasets-index', datasets[0].id)),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/editor_service_table_index_datasets.html")
        self.assertIsInstance(response.context["dataset_table"], DatasetTable)
        self.assertEqual(len(response.context["dataset_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["dataset_table"].page.object_list), 5)
