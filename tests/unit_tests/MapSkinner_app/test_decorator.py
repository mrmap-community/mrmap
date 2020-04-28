"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.04.20

"""
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.test import TestCase, Client, RequestFactory

from MapSkinner.decorator import log_proxy, check_permission
from service.models import Metadata, ProxyLog
from structure.models import Permission
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service, create_testuser
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD

TEST_URI = "http://test.com?request=GetTest"
TEST_URI_LOG_STRING = "/?request=GetTest"
MSG_PERMISSION_CHECK_FALSE_POSITIVE = "Testuser without permissions passed @check_permission"
MSG_PERMISSION_CHECK_TRUE_NEGATIVE = "Testuser with permissions did not pass @check_permission"


class DecoratorTestCase(TestCase):
    def setUp(self):
        self.default_user = create_testuser()
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        self.request_factory = RequestFactory()

        create_wms_service(
            self.user.get_groups().first(),
            1
        )

        # Setup for log proxy test
        self.metadata = Metadata.objects.all().first()
        self.metadata.use_proxy_uri = True
        self.metadata.log_proxy_access = True
        self.metadata.save()
        self.metadata.refresh_from_db()

    def test_check_permission(self):
        """ Tests whether the permission properly checks for user permissions

        Returns:

        """
        # Mock the usage of the decorator
        @check_permission(
            Permission(
                can_create_organization=True
            )
        )
        def test_function(request, *args, **kwargs):
            return HttpResponse()

        # Testuser permission check without any permissions must fail
        # Mock the request
        request = self.request_factory.get(
            TEST_URI,
        )
        request.user = self.default_user

        # add support for message middleware
        session_middleware = SessionMiddleware()
        session_middleware.process_request(request)
        request.session.save()
        request.META["HTTP_REFERER"] = "/"
        # adding messages
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = test_function(request)

        # Expect a redirect
        self.assertEqual(response.status_code, 302, msg=MSG_PERMISSION_CHECK_FALSE_POSITIVE)

        # Give Testuser group permission
        user_groups = self.default_user.get_groups()
        first_group = user_groups.first()
        first_group.role.permission.can_create_organization = True
        first_group.role.permission.save()

        # Testuser permission check with permission must run
        # Mock the request
        response = test_function(request)

        # Expect a 200
        self.assertEqual(response.status_code, 200, msg=MSG_PERMISSION_CHECK_TRUE_NEGATIVE)

        # Reset permission for other tests
        first_group.role.permission.can_create_organization = False
        first_group.role.permission.save()

    def test_log_proxy(self):
        """ Tests whether the responses of a service is properly logged

        Returns:

        """
        # Mock the usage of the decorator
        @log_proxy
        def test_function(request, *args, **kwargs):
            return HttpResponse()

        # Check that there is no ProxyLog record yet
        try:
            ProxyLog.objects.get(
                metadata=self.metadata
            )
            self.fail("@log_proxy did already exist before creation")
        except ObjectDoesNotExist:
            self.assertTrue(True)

        # Mock the request and logging
        request = self.request_factory.get(
            TEST_URI,
        )
        request.user = self.user
        test_function(request, metadata_id=self.metadata.id)

        # Check again for proxy log
        try:
            proxy_log = ProxyLog.objects.get(
                metadata=self.metadata
            )
        except ObjectDoesNotExist:
            self.fail(msg="@log_proxy did not create ProxyLog record")

        # Check that everything we provided is in its place
        self.assertIsInstance(proxy_log, ProxyLog, msg="proxy_log record is not a ProxyLog instance")
        self.assertEqual(proxy_log.user, self.user, msg="Another user has been related to the ProxyLog record")
        self.assertEqual(proxy_log.uri, TEST_URI_LOG_STRING, msg="The uri has not been stored correctly into the ProxyLog record")
