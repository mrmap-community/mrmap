import logging
import uuid

from django.contrib.messages import get_messages
from django.test import TestCase, Client
from django.urls import reverse

from MrMap.messages import NO_PERMISSION
from service.forms import UpdateOldToNewElementsForm
from service.helper.enums import DocumentEnum
from service.helper.service_comparator import ServiceComparator
from service.models import FeatureType, Document
from service.settings import NONE_UUID
from service.tables import PendingTaskTable, OgcServiceTable
from tests.baker_recipes.db_setup import *
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD
from tests.test_data import get_capabilitites_url


class ServiceIndexViewTestCase(TestCase):
    def setUp(self):
        self.logger = logging.getLogger('ServiceViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_services = create_wms_service(group=self.user.get_groups.first(), how_much_services=10)
        self.wfs_services = create_wfs_service(group=self.user.get_groups.first(), how_much_services=10)
        create_wms_service(is_update_candidate_for=self.wms_services[0].service, user=self.user,
                           group=self.user.get_groups.first())
        create_wfs_service(is_update_candidate_for=self.wfs_services[0].service, user=self.user,
                           group=self.user.get_groups.first())

class ServiceWmsIndexViewTestCase(TestCase):
    def setUp(self):
        self.logger = logging.getLogger('ServiceViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.get_groups.first(), how_much_services=10)

    def test_get_index_view(self):
        response = self.client.get(
            reverse('resource:wms-index', ),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="generic_views/generic_list.html")
        self.assertIsInstance(response.context["table"], OgcServiceTable)
        self.assertEqual(len(response.context["table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["table"].page.object_list), 5)


class ServiceWfsIndexViewTestCase(TestCase):
    def setUp(self):
        self.logger = logging.getLogger('ServiceViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(group=self.user.get_groups.first(), how_much_services=10)
        create_wfs_service(group=self.user.get_groups.first(), how_much_services=10)

    def test_get_index_view(self):
        response = self.client.get(
            reverse('resource:wfs-index', ),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="generic_views/generic_list.html")
        self.assertIsInstance(response.context["table"], OgcServiceTable)
        self.assertEqual(len(response.context["table"].rows), 10)
        # see if paging is working... only 5 elements by default should be listed
        self.assertEqual(len(response.context["table"].page.object_list), 5)


# ToDo: test service add view
class ServiceRemoveViewTestCase(TestCase):

    def setUp(self):
        self.logger = logging.getLogger('ServiceAddViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_service_metadatas = create_wms_service(group=self.user.get_groups.first(), how_much_services=1)
        self.wfs_service_metadatas = create_wfs_service(group=self.user.get_groups.first(), how_much_services=1)

    def test_remove_wms_service_view(self):
        metadata = self.wms_service_metadatas[0]
        response = self.client.post(metadata.remove_view_uri)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))

    def test_remove_wfs_service(self):
        metadata = self.wfs_service_metadatas[0]
        response = self.client.post(metadata.remove_view_uri)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home'))

    def test_permission_denied_remove(self):
        # remove permission to remove services
        perm = Permission.objects.get_or_create(name=PermissionEnum.CAN_REMOVE_RESOURCE.value)[0]
        for group in self.user.get_groups:
            group.role.permissions.remove(perm)

        response = self.client.post(
            self.wms_service_metadatas[0].remove_view_uri,
            HTTP_REFERER=self.wms_service_metadatas[0].remove_view_uri,
        )
        self.assertEqual(response.status_code, 302)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn(NO_PERMISSION, messages)


class ServiceActivateViewTestCase(TestCase):

    def setUp(self):
        self.logger = logging.getLogger('ServiceAddViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_service_metadatas = create_wms_service(group=self.user.get_groups.first(), how_much_services=1)

    def test_activate_service(self):
        md = self.wms_service_metadatas[0]
        response = self.client.post(md.activate_view_uri,
                                    data={'is_activate': 'on'})
        self.assertEqual(response.status_code, 302)

    def test_permission_denied_activate_service(self):
        # remove permission to remove services
        perm = Permission.objects.get_or_create(name=PermissionEnum.CAN_ACTIVATE_RESOURCE.value)[0]
        for group in self.user.get_groups:
            group.role.permissions.remove(perm)

        response = self.client.post(
            self.wms_service_metadatas[0].activate_view_uri,
            HTTP_REFERER=self.wms_service_metadatas[0].activate_view_uri,
        )
        self.assertEqual(response.status_code, 302)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertIn('You do not have permissions for this!', messages)


class ServiceDetailViewTestCase(TestCase):

    def setUp(self):
        self.logger = logging.getLogger('ServiceAddViewTestCase')
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.wms_service_metadatas = create_wms_service(group=self.user.get_groups.first(), how_much_services=1)
        self.wfs_service_metadatas = create_wfs_service(group=self.user.get_groups.first(), how_much_services=1)

    def test_get_detail_wms(self):
        response = self.client.get(reverse('resource:detail', args=[self.wms_service_metadatas[0].id]), )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="service/views/wms_tree.html")

    def test_get_detail_wms_sublayer(self):
        service = self.wms_service_metadatas[0].service
        sublayer_services = Service.objects.filter(
            parent_service=service
        )
        response = self.client.get(reverse('resource:detail', args=[sublayer_services[0].metadata.id]), )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="service/views/wms_tree.html")

    def test_get_detail_wms_sublayer_without_base_extending(self):
        service = self.wms_service_metadatas[0].service
        sublayer_services = Service.objects.filter(
            parent_service=service
        )
        response = self.client.get(reverse('resource:detail', args=[sublayer_services[0].metadata.id]), )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="service/views/wms_tree.html")

    def test_get_detail_wfs(self):
        response = self.client.get(reverse('resource:detail', args=[self.wfs_service_metadatas[0].id]), )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="service/views/wfs_tree.html")

    def test_get_detail_wfs_featuretype(self):
        service = self.wfs_service_metadatas[0].service
        featuretypes = FeatureType.objects.filter(
            parent_service=service
        )
        response = self.client.get(reverse('resource:detail', args=[featuretypes[0].metadata.id]), )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="service/views/featuretype.html")

    def test_get_detail_wfs_featuretype_without_base_extending(self):
        service = self.wfs_service_metadatas[0].service
        featuretypes = FeatureType.objects.filter(
            parent_service=service
        )
        response = self.client.get(reverse('resource:detail', args=[featuretypes[0].metadata.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, template_name="service/views/featuretype.html")

    def test_get_detail_404(self):
        response = self.client.get(reverse('resource:detail', args=[uuid.uuid4()]), )
        self.assertEqual(response.status_code, 404)

    def test_get_detail_context(self):
        response = self.client.get(reverse('resource:detail', args=[self.wms_service_metadatas[0].id]), )
        self.assertIsInstance(response.context['object'], Metadata)


class ServicePendingTaskViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_pending_task(self.user.get_groups.first(), 10)

    def test_get_pending_tasks_view(self):
        response = self.client.get(
            reverse('resource:pending-tasks', ),
        )
        self.assertEqual(response.status_code, 200, )
        self.assertTemplateUsed(response=response, template_name="generic_views/generic_list.html")
        self.assertIsInstance(response.context["table"], PendingTaskTable)
        self.assertEqual(len(response.context["table"].rows), 10)


class PendingUpdateServiceViewTestCase(TestCase):
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)

        self.wms_metadata = create_wms_service(group=self.user.get_groups.first(), how_much_services=1)[0]
        self.wms_update_candidate = create_wms_service(is_update_candidate_for=self.wms_metadata.service, group=self.user.get_groups[0], user=self.user)

        self.wfs_metadata = create_wfs_service(group=self.user.get_groups.first(), how_much_services=1)[0]
        self.wfs_update_candidate = create_wfs_service(is_update_candidate_for=self.wfs_metadata.service, group=self.user.get_groups[0], user=self.user)

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

        self.wms_metadata = create_wms_service(group=self.user.get_groups.first(), how_much_services=1)[0]
        self.wms_update_candidate = create_wms_service(is_update_candidate_for=self.wms_metadata.service, group=self.user.get_groups[0], user=self.user)

        self.wfs_metadata = create_wfs_service(group=self.user.get_groups.first(), how_much_services=1)[0]
        self.wfs_update_candidate = create_wfs_service(is_update_candidate_for=self.wfs_metadata.service, group=self.user.get_groups[0], user=self.user)

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

        self.wms_metadata = create_wms_service(group=self.user.get_groups.first(), how_much_services=1)[0]
        self.wms_update_candidate = create_wms_service(is_update_candidate_for=self.wms_metadata.service, group=self.user.get_groups[0], user=self.user)

        self.wfs_metadata = create_wfs_service(group=self.user.get_groups.first(), how_much_services=1)[0]
        self.wfs_update_candidate = create_wfs_service(is_update_candidate_for=self.wfs_metadata.service, group=self.user.get_groups[0], user=self.user)

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
        return
        # todo: refactor this test after refactoring of update resource process is done
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

        self.wms_metadata = create_wms_service(group=self.user.get_groups.first(), contact=self.organizations[0], how_much_services=1)[0]

        self.wfs_metadata = create_wfs_service(group=self.user.get_groups.first(), contact=self.organizations[0], how_much_services=1)[0]

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

        self.wms_metadata = create_wms_service(group=self.user.get_groups.first(), contact=self.organizations[0], how_much_services=1)[0]

        self.wfs_metadata = create_wfs_service(group=self.user.get_groups.first(), contact=self.organizations[0], how_much_services=1)[0]

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
        self.wms_metadata = create_wms_service(group=self.user.get_groups.first(), how_much_services=1)[0]

        # Activate metadata
        self.wms_metadata.is_active = True
        self.wms_metadata.save()

    def test_get_dataset_metadata(self):
        dataset_mds = self.wms_metadata.get_related_dataset_metadatas()
        for dataset_md in dataset_mds:
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
            group=self.user.get_groups.first(),
            how_much_services=1,
            contact=self.organizations[0]
        )[0]

    def test_get_service_metadata(self):
        response = self.client.get(
            reverse('resource:get-service-metadata', args=(self.wms_metadata.id,))
        )
        self.assertEqual(response.status_code, 200)

