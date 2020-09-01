import logging
import uuid

from django.contrib.messages import get_messages
from django.test import TestCase, Client
from django.urls import reverse
from MrMap.messages import SERVICE_DEACTIVATED_TEMPLATE, SERVICE_ACTIVATED_TEMPLATE
from service.forms import UpdateOldToNewElementsForm
from service.helper.enums import OGCServiceEnum
from service.helper.service_comparator import ServiceComparator
from service.models import FeatureType, Metadata
from service.settings import NONE_UUID
from service.tables import WfsServiceTable, PendingTasksTable, WmsTableWms
from service.tasks import async_activate_service
from structure.models import GroupActivity
from tests.baker_recipes.db_setup import *
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD
from tests.test_data import get_capabilitites_url


class ServiceIndexViewTestCase(TestCase):
    def setUp(self):
        self.logger = logging.getLogger('ServiceViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_services = create_wms_service(group=self.user.get_groups().first(), how_much_services=10)
        self.wfs_services = create_wfs_service(group=self.user.get_groups().first(), how_much_services=10)
        create_wms_service(is_update_candidate_for=self.wms_services[0].service, user=self.user,
                           group=self.user.get_groups().first())
        create_wfs_service(is_update_candidate_for=self.wfs_services[0].service, user=self.user,
                           group=self.user.get_groups().first())

    def test_get_index_view(self):
        response = self.client.get(
            reverse('resource:index', ),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/index.html")
        self.assertIsInstance(response.context["wms_table"], WmsTableWms)
        self.assertEqual(len(response.context["wms_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["wms_table"].page.object_list), 5)

        self.assertIsInstance(response.context["wfs_table"], WfsServiceTable)
        self.assertEqual(len(response.context["wfs_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["wfs_table"].page.object_list), 5)

        self.assertIsInstance(response.context["pt_table"], PendingTasksTable)


class ServiceWmsIndexViewTestCase(TestCase):
    def setUp(self):
        self.logger = logging.getLogger('ServiceViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.get_groups().first(), how_much_services=10)

    def test_get_index_view(self):
        response = self.client.get(
            reverse('resource:wms-index', ),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/wms_index.html")
        self.assertIsInstance(response.context["wms_table"], WmsTableWms)
        self.assertEqual(len(response.context["wms_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["wms_table"].page.object_list), 5)

        self.assertIsInstance(response.context["pt_table"], PendingTasksTable)


class ServiceWfsIndexViewTestCase(TestCase):
    def setUp(self):
        self.logger = logging.getLogger('ServiceViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.get_groups().first(), how_much_services=10)
        create_wfs_service(group=self.user.get_groups().first(), how_much_services=10)

    def test_get_index_view(self):
        response = self.client.get(
            reverse('resource:wfs-index', ),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="views/wfs_index.html")
        self.assertIsInstance(response.context["wfs_table"], WfsServiceTable)
        self.assertEqual(len(response.context["wfs_table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["wfs_table"].page.object_list), 5)
        self.assertIsInstance(response.context["pt_table"], PendingTasksTable)

# ToDo: test service add view

class ServiceRemoveViewTestCase(TestCase):

    def setUp(self):
        self.logger = logging.getLogger('ServiceAddViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_service_metadatas = create_wms_service(group=self.user.get_groups().first(), how_much_services=1)
        self.wfs_service_metadatas = create_wfs_service(group=self.user.get_groups().first(), how_much_services=1)

    def test_remove_wms_service(self):
        post_data = {
            'is_confirmed': 'on'
        }
        metadata = self.wms_service_metadatas[0]
        response = self.client.post(reverse('resource:remove', args=[metadata.id])+"?current-view=resource:index", data=post_data)
        self.assertEqual(response.status_code, 303)

        metadata.refresh_from_db()
        self.assertTrue(metadata.is_deleted, msg="Metadata is not marked as deleted.")

        sub_elements = metadata.service.subelements
        for sub_element in sub_elements:
            sub_metadata = sub_element.metadata
            self.assertTrue(sub_metadata.is_deleted, msg="Metadata of subelement is not marked as deleted.")

        self.assertEqual(GroupActivity.objects.all().count(), 1)

    def test_remove_wfs_service(self):
        post_data = {
            'is_confirmed': 'on'
        }
        metadata = self.wfs_service_metadatas[0]
        response = self.client.post(reverse('resource:remove', args=[self.wfs_service_metadatas[0].id])+"?current-view=resource:index", data=post_data)
        self.assertEqual(response.status_code, 303)

        metadata.refresh_from_db()
        self.assertTrue(metadata.is_deleted, msg="Metadata is not marked as deleted.")

        sub_elements = metadata.service.subelements
        for sub_element in sub_elements:
            sub_metadata = sub_element.metadata
            self.assertTrue(sub_metadata.is_deleted, msg="Metadata of subelement is not marked as deleted.")

        self.assertEqual(GroupActivity.objects.all().count(), 1)

    def test_remove_service_invalid_form(self):

        response = self.client.post(reverse('resource:remove', args=[self.wms_service_metadatas[0].id])+"?current-view=resource:index",)
        self.assertEqual(response.status_code, 422)

    def test_permission_denied_remove(self):

        # remove permission to remove services
        perm = self.user.get_groups()[0].role.permission
        perm.can_remove_resource = False
        perm.save()

        response = self.client.post(
            reverse(
                'resource:remove',
                args=[str(self.wms_service_metadatas[0].id)]
            ),
            HTTP_REFERER=reverse(
                'resource:remove',
                args=[str(self.wms_service_metadatas[0].id)]
            ),
        )
        self.assertEqual(response.status_code, 302)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn('You do not have permissions for this!', messages)


class ServiceActivateViewTestCase(TestCase):

    def setUp(self):
        self.logger = logging.getLogger('ServiceAddViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_service_metadatas = create_wms_service(group=self.user.get_groups().first(), how_much_services=1)

    def test_activate_service(self):

        md = self.wms_service_metadatas[0]
        response = self.client.post(reverse('resource:activate', args=[md.id])+"?current-view=resource:index",
                                    data={'is_confirmed': 'True'})
        self.assertEqual(response.status_code, 303)
        messages = [m.message for m in get_messages(response.wsgi_request)]

        activated_status = md.is_active
        if activated_status:
            self.assertIn(SERVICE_DEACTIVATED_TEMPLATE.format(self.wms_service_metadatas[0].title), messages)
        else:
            self.assertIn(SERVICE_ACTIVATED_TEMPLATE.format(self.wms_service_metadatas[0].title), messages)

    def test_permission_denied_activate_service(self):
        # remove permission to remove services
        perm = self.user.get_groups()[0].role.permission
        perm.can_activate_resource = False
        perm.save()

        md = self.wms_service_metadatas[0]
        response = self.client.post(reverse('resource:activate',
                                            args=[str(md.id)]),
                                    HTTP_REFERER=reverse('resource:activate', args=[str(md.id)]), )
        self.assertEqual(response.status_code, 302)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn('You do not have permissions for this!', messages)


class ServiceDetailViewTestCase(TestCase):

    def setUp(self):
        self.logger = logging.getLogger('ServiceAddViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_service_metadatas = create_wms_service(group=self.user.get_groups().first(), how_much_services=1)
        self.wfs_service_metadatas = create_wfs_service(group=self.user.get_groups().first(), how_much_services=1)

    def test_get_detail_wms(self):
        response = self.client.get(reverse('resource:detail', args=[self.wms_service_metadatas[0].id]), )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="views/detail.html")

    def test_get_detail_wms_sublayer(self):
        service = self.wms_service_metadatas[0].service
        sublayer_services = Service.objects.filter(
            parent_service=service
        )
        response = self.client.get(reverse('resource:detail', args=[sublayer_services[0].metadata.id]), )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="views/sublayer_detail.html")

    def test_get_detail_wms_sublayer_without_base_extending(self):
        service = self.wms_service_metadatas[0].service
        sublayer_services = Service.objects.filter(
            parent_service=service
        )
        response = self.client.get(reverse('resource:detail', args=[sublayer_services[0].metadata.id]) + '?no-base', )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="views/sublayer_detail_no_base.html")

    def test_get_detail_wfs(self):
        response = self.client.post(reverse('resource:detail', args=[self.wfs_service_metadatas[0].id]), )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="views/detail.html")

    def test_get_detail_wfs_featuretype(self):
        service = self.wfs_service_metadatas[0].service
        featuretypes = FeatureType.objects.filter(
            parent_service=service
        )
        response = self.client.get(reverse('resource:detail', args=[featuretypes[0].metadata.id]), )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="views/featuretype_detail.html")

    def test_get_detail_wfs_featuretype_without_base_extending(self):
        service = self.wfs_service_metadatas[0].service
        featuretypes = FeatureType.objects.filter(
            parent_service=service
        )
        response = self.client.get(reverse('resource:detail', args=[featuretypes[0].metadata.id]) + '?no-base', )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="views/featuretype_detail_no_base.html")

    def test_get_detail_404(self):
        response = self.client.post(reverse('resource:detail', args=[uuid.uuid4()]), )
        self.assertEqual(response.status_code, 404)

    def test_get_detail_context(self):
        response = self.client.get(reverse('resource:detail', args=[self.wms_service_metadatas[0].id]), )
        self.assertIsInstance(response.context['service_md'], Metadata)


class ServicePendingTaskViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_pending_task(self.user.get_groups().first(), 10)

    def test_get_pending_tasks_view(self):
        response = self.client.get(
            reverse('resource:pending-tasks', ),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="includes/pending_tasks.html")
        self.assertIsInstance(response.context["pt_table"], PendingTasksTable)
        self.assertEqual(len(response.context["pt_table"].rows), 10)


class NewUpdateServiceViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)

        self.wms_metadatas = create_wms_service(group=self.user.get_groups().first(), how_much_services=1)

    def test_get_update_service_view(self):
        response = self.client.get(
            reverse('resource:new-pending-update', args=(self.wms_metadatas[0].id,))+"?current-view=resource:index",
        )
        self.assertEqual(response.status_code, 200)

    def test_post_valid_update_service_page1(self):
        params = {
            'page': '1',
            'get_capabilities_uri': get_capabilitites_url().get('valid'),
        }
        response = self.client.post(
            reverse('resource:new-pending-update', args=(self.wms_metadatas[0].id,)),
            data=params
        )
        self.assertEqual(response.status_code, 303)
        try:
            Service.objects.get(is_update_candidate_for=self.wms_metadatas[0].service.id)
        except ObjectDoesNotExist:
            self.fail("No update candidate were found for the service.")

    def test_post_invalid_no_service_update_service_page1(self):
        params = {
            'page': '1',
            'get_capabilities_uri': get_capabilitites_url().get('invalid_no_service'),
        }

        response = self.client.post(
            reverse('resource:new-pending-update', args=(self.wms_metadatas[0].id,))+"?current-view=resource:index",
            data=params
        )

        self.assertEqual(response.status_code, 422)  # 'The given uri is not valid cause there is no service parameter.'

    def test_post_invalid_service_type_update_service_page1(self):
        params = {
            'page': '1',
            'get_capabilities_uri': get_capabilitites_url().get('valid_wfs_version_202'),
        }

        response = self.client.post(
            reverse('resource:new-pending-update', args=(self.wms_metadatas[0].id,))+"?current-view=resource:index",
            data=params
        )

        self.assertEqual(response.status_code, 422)

    def test_post_invalid_update_candidate_exists_update_service_page1(self):
        params = {
            'page': '1',
            'get_capabilities_uri': get_capabilitites_url().get('valid'),
        }
        create_wms_service(is_update_candidate_for=self.wms_metadatas[0].service, group=self.user.get_groups()[0], user=self.user)

        response = self.client.post(
            reverse('resource:new-pending-update', args=(self.wms_metadatas[0].id,))+"?current-view=resource:index",
            data=params
        )
        self.assertEqual(response.status_code, 422)  # "There are still pending update requests from user '{}' for this service.".format(self.user)


class PendingUpdateServiceViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)

        self.wms_metadata = create_wms_service(group=self.user.get_groups().first(), how_much_services=1)[0]
        self.wms_update_candidate = create_wms_service(is_update_candidate_for=self.wms_metadata.service, group=self.user.get_groups()[0], user=self.user)

        self.wfs_metadata = create_wfs_service(group=self.user.get_groups().first(), how_much_services=1)[0]
        self.wfs_update_candidate = create_wfs_service(is_update_candidate_for=self.wfs_metadata.service, group=self.user.get_groups()[0], user=self.user)

    def test_get_pending_update_wms_service_view(self):
        response = self.client.get(
            reverse('resource:pending-update', args=(self.wms_metadata.id,)),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response=response, template_name="views/service_update.html")
        self.assertIsInstance(response.context["current_service"], Service)
        self.assertIsInstance(response.context["update_service"], Service)
        self.assertIsInstance(response.context["diff_elements"], dict)
        self.assertIsInstance(response.context["update_confirmation_form"], UpdateOldToNewElementsForm)

    def test_get_pending_update_wfs_service_view(self):
        response = self.client.get(
            reverse('resource:pending-update', args=(self.wfs_metadata.id,)),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response=response, template_name="views/service_update.html")
        self.assertIsInstance(response.context["current_service"], Service)
        self.assertIsInstance(response.context["update_service"], Service)
        self.assertIsInstance(response.context["diff_elements"], dict)
        self.assertIsInstance(response.context["update_confirmation_form"], UpdateOldToNewElementsForm)


class DismissPendingUpdateServiceViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)

        self.wms_metadata = create_wms_service(group=self.user.get_groups().first(), how_much_services=1)[0]
        self.wms_update_candidate = create_wms_service(is_update_candidate_for=self.wms_metadata.service, group=self.user.get_groups()[0], user=self.user)

        self.wfs_metadata = create_wfs_service(group=self.user.get_groups().first(), how_much_services=1)[0]
        self.wfs_update_candidate = create_wfs_service(is_update_candidate_for=self.wfs_metadata.service, group=self.user.get_groups()[0], user=self.user)

    def test_get_dismiss_pending_update_wms_service_view(self):
        response = self.client.get(
            reverse('resource:dismiss-pending-update', args=(self.wms_metadata.id,)),
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.url, reverse('resource:pending-update', args=(self.wms_metadata.id,)))

    def test_get_dismiss_pending_update_wfs_service_view(self):
        response = self.client.get(
            reverse('resource:dismiss-pending-update', args=(self.wfs_metadata.id,)),
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.url, reverse('resource:pending-update', args=(self.wfs_metadata.id,)))

    def test_post_dismiss_pending_update_wms_service_view(self):
        response = self.client.post(
            reverse('resource:dismiss-pending-update', args=(self.wms_metadata.id,)),
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.url, reverse('resource:detail', args=(self.wms_metadata.id,)))

    def test_post_dismiss_pending_update_wfs_service_view(self):
        response = self.client.post(
            reverse('resource:dismiss-pending-update', args=(self.wfs_metadata.id,)),
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.url, reverse('resource:detail', args=(self.wfs_metadata.id,)))


class RunUpdateServiceViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)

        self.wms_metadata = create_wms_service(group=self.user.get_groups().first(), how_much_services=1)[0]
        self.wms_update_candidate = create_wms_service(is_update_candidate_for=self.wms_metadata.service, group=self.user.get_groups()[0], user=self.user)

        self.wfs_metadata = create_wfs_service(group=self.user.get_groups().first(), how_much_services=1)[0]
        self.wfs_update_candidate = create_wfs_service(is_update_candidate_for=self.wfs_metadata.service, group=self.user.get_groups()[0], user=self.user)

    def test_get_run_update_wms_service_view(self):
        response = self.client.get(
            reverse('resource:run-update', args=(self.wms_metadata.id,)),
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.url, reverse('resource:pending-update', args=(self.wms_metadata.id,)))

    def test_get_run_update_wfs_service_view(self):
        response = self.client.get(
            reverse('resource:run-update', args=(self.wfs_metadata.id,)),
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.url, reverse('resource:pending-update', args=(self.wfs_metadata.id,)))

    def test_post_run_update_wms_service_view(self):
        comparator = ServiceComparator(service_a=self.wms_update_candidate[0].service, service_b=self.wms_metadata.service)
        diff = comparator.compare_services()
        diff_elements = diff.get("layers")
        new_elements = diff_elements.get("new")

        data = {}
        for element in new_elements:
            data.update({'new_elem_{}'.format(element.metadata.identifier): NONE_UUID})

        response = self.client.post(
            reverse('resource:run-update', args=(str(self.wms_metadata.id),)),
            data=data,
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.url, reverse('resource:detail', args=(self.wms_metadata.id,)))

    def test_post_invalid_run_update_wms_service_view(self):
        comparator = ServiceComparator(service_a=self.wms_update_candidate[0].service,
                                       service_b=self.wms_metadata.service)
        diff = comparator.compare_services()
        diff_elements = diff.get("layers")
        new_elements = diff_elements.get("new")

        data = {}
        for element in new_elements:
            data.update({'new_elem_{}'.format(element.metadata.identifier): NONE_UUID})

        response = self.client.post(
            reverse('resource:run-update', args=(self.wms_metadata.id,)),
        )

        self.assertEqual(response.status_code, 422)
        self.assertFormError(response, 'update_confirmation_form', next(iter(data)), 'This field is required.' )

    def test_post_run_update_wfs_service_view(self):
        comparator = ServiceComparator(service_a=self.wfs_update_candidate[0].service,
                                       service_b=self.wfs_metadata.service)
        diff = comparator.compare_services()
        diff_elements = diff.get("feature_types")
        new_elements = diff_elements.get("new")

        data = {}
        for element in new_elements:
            data.update({'new_elem_{}'.format(element.metadata.identifier): NONE_UUID})

        response = self.client.post(
            reverse('resource:run-update', args=(str(self.wfs_metadata.id),)),
            data=data
        )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.url, reverse('resource:detail', args=(self.wfs_metadata.id,)))


class GetMetadataHtmlViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.organizations = create_non_autogenerated_orgas(user=self.user)

        self.wms_metadata = create_wms_service(group=self.user.get_groups().first(), contact=self.organizations[0], how_much_services=1)[0]

        self.wfs_metadata = create_wfs_service(group=self.user.get_groups().first(), contact=self.organizations[0], how_much_services=1)[0]

    def test_get_metadata_html_for_wms(self):
        response = self.client.get(
            reverse('resource:get-metadata-html', args=(self.wms_metadata.id,))
        )
        self.assertEqual(response.status_code, 200)

    def test_get_metadata_html_for_layer(self):
        response = self.client.get(
            reverse('resource:get-metadata-html', args=(self.wms_metadata.service.root_layer.metadata.id,))
        )
        self.assertEqual(response.status_code, 200)

    def test_get_metadata_html_for_wfs(self):
        response = self.client.get(
            reverse('resource:get-metadata-html', args=(self.wfs_metadata.id,))
        )
        self.assertEqual(response.status_code, 200)

    def test_get_metadata_html_for_featuretype(self):
        featuretypes = FeatureType.objects.filter(
            parent_service=self.wfs_metadata.service
        )
        response = self.client.get(
            reverse('resource:get-metadata-html', args=(featuretypes[0].metadata.id,))
        )
        self.assertEqual(response.status_code, 200)


class GetServicePreviewViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.organizations = create_non_autogenerated_orgas(user=self.user)

        self.wms_metadata = create_wms_service(group=self.user.get_groups().first(), contact=self.organizations[0], how_much_services=1)[0]

        self.wfs_metadata = create_wfs_service(group=self.user.get_groups().first(), contact=self.organizations[0], how_much_services=1)[0]

    def test_get_preview_for_wms(self):
        # ToDo: can't be tested as unit test cause of : img = operation_request_handler.get_operation_response(post_data=data)  # img is returned as a byte code
        return
        response = self.client.get(
            reverse('resource:get-service-metadata-preview', args=(self.wms_metadata.id,))
        )
        self.assertEqual(response.status_code, 200)


class GetDatasetMetadataViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_metadata = create_wms_service(group=self.user.get_groups().first(), how_much_services=1)[0]

        # Activate metadata
        async_activate_service(self.wms_metadata.id, self.user.id, True)

    def test_get_dataset_metadata_redirect_to_dataset(self):
        response = self.client.get(
            reverse('resource:get-dataset-metadata', args=(self.wms_metadata.id,))
        )
        self.assertEqual(response.status_code, 302)

    def test_get_dataset_metadata(self):
        dataset_md = self.wms_metadata.related_metadata.get(
            metadata_to__metadata_type=OGCServiceEnum.DATASET.value
        )
        dataset_md = dataset_md.metadata_to

        response = self.client.get(
            reverse('resource:get-dataset-metadata', args=(dataset_md.id,))
        )
        self.assertEqual(response.status_code, 200)


class GetServiceMetadataViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.organizations = create_non_autogenerated_orgas(user=self.user)
        self.wms_metadata = create_wms_service(
            group=self.user.get_groups().first(),
            how_much_services=1,
            contact=self.organizations[0]
        )[0]

    def test_get_service_metadata(self):
        response = self.client.get(
            reverse('resource:get-service-metadata', args=(self.wms_metadata.id,))
        )
        self.assertEqual(response.status_code, 200)
