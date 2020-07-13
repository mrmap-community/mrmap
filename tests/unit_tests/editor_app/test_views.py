"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 27.04.20

"""
from django.contrib.messages import get_messages
from django.test import TestCase, Client
from django.urls import reverse

from MrMap.messages import METADATA_IS_ORIGINAL
from editor.forms import MetadataEditorForm

from service.helper.enums import ResourceOriginEnum, MetadataEnum
from service.models import Metadata
from service.tables import DatasetTable
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service, create_public_organization
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
        metadata = Metadata.objects.filter(
            metadata_type=MetadataEnum.SERVICE.value
        ).first()
        response = self.client.get(
            reverse(EDITOR_METADATA_EDITOR_NAME, args=(str(metadata.id),))+"?current-view=service:index",
        )
        self.assertEqual(response.status_code, 200, )
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
            reverse(EDITOR_ACCESS_EDITOR_NAME, args=(str(metadata.id),))+"?current-view=service:index",
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/editor_edit_access_index.html")
        self.assertEqual(response.context["service_metadata"], metadata)
        # No form to test

    def test_get_access_geometry_form_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        metadata = Metadata.objects.filter(
            metadata_type=MetadataEnum.SERVICE.value
        ).first()
        response = self.client.get(
            reverse(EDITOR_ACCESS_GEOMETRY_EDITOR_NAME, args=(str(metadata.id),)),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/access_geometry_form.html")
        # No form to test


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
            reverse(EDITOR_DATASET_WIZARD_NEW,)+"?current-view=service:datasets-index",
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/datasets_index.html")
        self.assertIsInstance(response.context["dataset_table"], DatasetTable)
        self.assertEqual(len(response.context["dataset_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["dataset_table"].page.object_list), 5)


class EditorDatasetWizardInstanceViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.organization = create_public_organization(user=self.user)
        self.wms_services = create_wms_service(group=self.user.get_groups().first(),
                                               how_much_services=10,
                                               contact=self.organization[0])

    def test_get_wizard_instance_view(self):
        """ Test for checking whether the view is correctly rendered or not

        Returns:

        """
        datasets = self.user.get_datasets_as_qs()
        url = reverse(EDITOR_DATASET_WIZARD_EDIT, args=[datasets[0].id])+"?current-view=service:datasets-index"
        response = self.client.get(
            url,
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/datasets_index.html")
        self.assertIsInstance(response.context["dataset_table"], DatasetTable)
        self.assertEqual(len(response.context["dataset_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["dataset_table"].page.object_list), 5)

    def test_step_and_save_wizard_instance_view(self):
        datasets = self.user.get_datasets_as_qs()
        step_post_params = {"wizard_goto_step": "responsible party",
                            "dataset_wizard-current_step": "identification",
                            "identification-is_form_update": "False",
                            "identification-title": "Ahrhutstrasse",
                            "identification-abstract": "Bebauungsplan \"Ahrhutstraße\"",
                            "identification-language_code": "ger",
                            "identification-character_set_code": "utf8",
                            "identification-date_stamp": "2020-06-23",
                            "identification-created_by": self.user.get_groups().first().id}

        step2_post_params = {"wizard_goto_step": "classification",
                             "dataset_wizard-current_step": "responsible party",
                             "responsible party-is_form_update": "False",
                             "responsible party-organization": "",
                             }

        save_post_params = {"dataset_wizard-current_step": "classification",
                            "classification-is_form_update": "False",
                            "classification-keywords": [],
                            "wizard_save": "True"}
        url = reverse(EDITOR_DATASET_WIZARD_EDIT, args=[datasets[0].id])+"?current-view=service:datasets-index"
        step_response = self.client.post(url,
                                         HTTP_REFERER=reverse('service:datasets-index'),
                                         data=step_post_params,)
        self.assertEqual(step_response.status_code, 200, )
        self.assertTrue('name="dataset_wizard-current_step" value="responsible party"' in step_response.context['rendered_modal'], msg='The current step was not responsible party ')
        self.assertTemplateUsed(response=step_response, template_name="views/datasets_index.html")

        step2_response = self.client.post(reverse('editor:dataset-metadata-wizard-instance',
                                                  args=(datasets[0].id,))+"?current-view=service:datasets-index",
                                          HTTP_REFERER=reverse('service:datasets-index'),
                                          data=step2_post_params,)

        self.assertEqual(step2_response.status_code, 200, )
        self.assertTrue('name="dataset_wizard-current_step" value="classification"' in step2_response.context['rendered_modal'], msg='The current step was not classification ')
        self.assertTemplateUsed(response=step2_response, template_name="views/datasets_index.html")

        save_response = self.client.post(reverse('editor:dataset-metadata-wizard-instance',
                                                 args=(datasets[0].id,))+"?current-view=service:datasets-index",
                                         HTTP_REFERER=reverse('service:datasets-index'),
                                         data=save_post_params,)

        # 303 is returned due to the FormWizard
        self.assertEqual(save_response.status_code, 303, )
        self.assertEqual('/service/datasets/', save_response.url)


class EditorDatasetRemoveInstanceViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_services = create_wms_service(
            group=self.user.get_groups().first(),
            how_much_services=1,
            md_relation_origin=ResourceOriginEnum.EDITOR.value
        )

    def test_remove_instance_view(self):
        """ Test for checking whether the dataset is removed or not

        Returns:

        """
        datasets = self.user.get_datasets_as_qs()
        post_data = {'is_confirmed': 'True'}

        response = self.client.post(
            reverse('editor:remove-dataset-metadata', args=(datasets[0].id, ))+"?current-view=service:index",
            data=post_data
        )

        self.assertEqual(response.status_code, 303, )
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn("Dataset successfully deleted.", messages)


class EditorRestoreDatasetViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_services = create_wms_service(group=self.user.get_groups().first(), how_much_services=10)

    def test_restore_non_custom_instance_view(self):
        """ Test for checking whether the dataset is restored or not

        Returns:

        """
        datasets = self.user.get_datasets_as_qs()

        response = self.client.post(
            reverse('editor:restore-dataset-metadata', args=(datasets[0].id,))+"?current-view=service:index",
            HTTP_REFERER=reverse('service:index'),
            data={'is_confirmed': 'True'},
        )

        self.assertEqual(response.status_code, 303, )
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn(METADATA_IS_ORIGINAL, messages)
