from django.test import TestCase
from registry.models.security import WebMapServiceOperation
from registry.views.security import WebMapServiceOperationViewSet
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory


class WebMapServiceOperationOrderingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        WebMapServiceOperation.objects.get_or_create(value=20)
        WebMapServiceOperation.objects.get_or_create(value=21)

    def test_ordering_by_json_api_id(self):
        for ordering, expected in [("id", [20, 21]), ("-id", [21, 20]),
                                   ("value", [20, 21])]:
            with self.subTest(ordering=ordering):
                view = WebMapServiceOperationViewSet()
                view.request = Request(APIRequestFactory().get(
                    "/api/registry/security/wms-operations", {"sort": ordering}
                ))
                view.action = "list"
                queryset = view.filter_queryset(view.get_queryset())
                self.assertEqual(list(queryset.values_list("value", flat=True)), expected)


class AllowedWebMapServiceOperationGroupFilterTest(TestCase):
    fixtures = ['test_users.json', 'test_keywords.json', 'test_wms.json']

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Group
        from registry.models.security import AllowedWebMapServiceOperation
        from registry.models.service import WebMapService

        cls.group = Group.objects.create(name='Policy test group')
        other = Group.objects.create(name='Other policy group')
        service = WebMapService.objects.get(pk='cd16cc1f-3abb-4625-bb96-fbe80dbe23e3')
        cls.shared = AllowedWebMapServiceOperation.objects.create(secured_service=service)
        cls.specific = AllowedWebMapServiceOperation.objects.create(secured_service=service)
        cls.specific.allowed_groups.set([cls.group, other])
        cls.unrelated = AllowedWebMapServiceOperation.objects.create(secured_service=service)
        cls.unrelated.allowed_groups.set([other])

    def test_group_filter_includes_shared_rules_without_duplicates(self):
        from registry.filters.security import AllowedWebMapServiceOperationFilterSet
        from registry.models.security import AllowedWebMapServiceOperation

        filters = AllowedWebMapServiceOperationFilterSet(
            data={'access_group': self.group.pk},
            queryset=AllowedWebMapServiceOperation.objects.all(),
        )
        self.assertTrue(filters.is_valid())
        self.assertCountEqual(list(filters.qs), [self.shared, self.specific])

    def test_missing_group_filter_preserves_all_rules(self):
        from registry.filters.security import AllowedWebMapServiceOperationFilterSet
        from registry.models.security import AllowedWebMapServiceOperation

        filters = AllowedWebMapServiceOperationFilterSet(
            data={}, queryset=AllowedWebMapServiceOperation.objects.all(),
        )
        self.assertCountEqual(list(filters.qs), [self.shared, self.specific, self.unrelated])

    def test_group_filter_schema_identifies_the_related_resource(self):
        from extras.schema import CustomOperationId
        from registry.filters.security import AllowedWebMapServiceOperationFilterSet
        from registry.views.security import AllowedWebMapServiceOperationViewSet

        schema = CustomOperationId()
        schema.view = AllowedWebMapServiceOperationViewSet()
        parameter = {}
        schema._patch_extend_filter_parameter(
            AllowedWebMapServiceOperationFilterSet.base_filters['access_group'], parameter,
        )
        self.assertEqual(parameter['x-jsonapi-related-resource-type'], 'Group')
        self.assertEqual(parameter['x-jsonapi-filter-lookup-expression'], 'exact')

    def test_user_filter_combines_all_groups_and_shared_rules(self):
        from django.contrib.auth import get_user_model
        from registry.filters.security import AllowedWebMapServiceOperationFilterSet
        from registry.models.security import AllowedWebMapServiceOperation

        user = get_user_model().objects.create_user(username='policy-user')
        user.groups.set(self.specific.allowed_groups.all())
        filters = AllowedWebMapServiceOperationFilterSet(
            data={'access_user': user.pk}, queryset=AllowedWebMapServiceOperation.objects.all(),
        )
        self.assertTrue(filters.is_valid())
        self.assertCountEqual(list(filters.qs), [self.shared, self.specific, self.unrelated])
        user.groups.clear()
        filters = AllowedWebMapServiceOperationFilterSet(
            data={'access_user': user.pk}, queryset=AllowedWebMapServiceOperation.objects.all(),
        )
        self.assertCountEqual(list(filters.qs), [self.shared])

    def test_user_filter_schema_identifies_the_related_resource(self):
        from extras.schema import CustomOperationId
        from registry.filters.security import AllowedWebMapServiceOperationFilterSet
        from registry.views.security import AllowedWebMapServiceOperationViewSet

        schema = CustomOperationId()
        schema.view = AllowedWebMapServiceOperationViewSet()
        parameter = {}
        schema._patch_extend_filter_parameter(
            AllowedWebMapServiceOperationFilterSet.base_filters['access_user'], parameter,
        )
        self.assertEqual(parameter['x-jsonapi-related-resource-type'], 'User')
        self.assertEqual(parameter['x-jsonapi-filter-lookup-expression'], 'exact')
