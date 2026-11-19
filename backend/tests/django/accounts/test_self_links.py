"""The self link of a permission names the permission, not a user (#1475).

`PermissionSerializer.url` was the user serializer's field copied over: it
reversed `accounts:user-detail`, so every permission answered a self link
below `/api/accounts/users/`. That route reverses for any pk string -- DRF
never asks whether the number is a user -- so the link of a permission either
answers 404 or, worse, a user whose id happens to be the permission's id. The
route this resource is registered under is `accounts:permission-detail`
(`accounts/urls.py`, `/api/accounts/permissions`).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"


class PermissionSelfLinkTest(TestCase):
    """`links.self` of `/api/accounts/permissions` (#1475)."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_superuser(
            username="permission-links", password="test"))
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def test_self_link_names_the_permissions_route(self):
        permission = Permission.objects.get(codename="add_user")

        response = self.client.get(f"/api/accounts/permissions/{permission.pk}")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["data"]["links"]["self"],
            f"http://testserver/api/accounts/permissions/{permission.pk}")
