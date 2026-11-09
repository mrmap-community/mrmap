"""Keeps the object permissions MrMap writes out of guardian's shared table.

Guardian stores the object permission of *every* model in one table and names the
object by ``content_type`` and the **text** of its primary key. For a lookup it
makes both sides comparable by casting, so for a model whose primary key is a uuid
the shared column becomes ``CAST(CAST(object_pk AS uuid) AS text)``. Whether
PostgreSQL evaluates that expression only for the rows the query is about or for
the rows of every other model in the table is a decision of the query plan: one
row of a model with an integer primary key can answer the permission lookup of a
service with ``invalid input syntax for type uuid``.

The models of the permission bootstrap got their own tables with the migrations
``accounts/0002`` and ``registry/0030``, see ``accounts/models/guardian.py``. What
this module pins for the rest of the repository:

* the fixtures which write an object permission write the table of the model they
  grant on - ``registry/fixtures/test_mapcontext.json`` and
  ``registry/fixtures/test_monitoring.json`` named an integer primary key in the
  shared table, and the rows which are already in it decide which future query
  500s;
* nothing which is answered from a table of its own stays behind in the shared
  table: guardian does not read it there, so such a row is a lost grant *and* the
  text a uuid lookup has to cast;
* every kind of service the reads which scope by permission ask answers from a
  table of its own - ``registry.querys.alerts.collect_service_alerts`` and the
  visibility of the background activity in ``notify/managers.py`` ask all three
  kinds, also the catalogue nobody grants anything on today.

The guard for *every* model, including the one of a future role, is the subject of
#735; this module only covers what the repository writes and asks today.
"""
import importlib
import uuid

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from guardian.models import GroupObjectPermission, UserObjectPermission
from guardian.utils import (get_group_obj_perms_model,
                            get_user_obj_perms_model)
from registry.models.guardian import (MapContextGroupObjectPermission,
                                      MapContextLayerGroupObjectPermission,
                                      WebMapServiceMonitoringSettingGroupObjectPermission)
from registry.querys.alerts import SERVICE_KIND_OF, refresh_service_alerts
from rest_framework.test import APIClient

from accounts.models.guardian import OrganizationGroupObjectPermission
from accounts.models.groups import Organization

#: the fixtures whose permission rows are moved out of the shared table
FIXTURES = ["test_users.json", "test_keywords.json", "test_crs.json",
            "test_wms.json", "test_mapcontext.json", "test_monitoring.json"]

#: the grants of ``test_mapcontext.json`` on the map applications themselves
MAPCONTEXT_GRANTS = {
    ("change_mapcontext", "Group1", 1),
    ("delete_mapcontext", "Group1", 1),
    ("change_mapcontext", "Group2", 2),
    ("delete_mapcontext", "Group2", 2),
}

#: the layers of the second map application, which that fixture grants to Group2
GRANTED_LAYERS = [6, 7, 8, 9, 10, 11]

#: the layer of the second map application a scenario of the api changes
GRANTED_LAYER = 8

JSONAPI = "application/vnd.api+json"

#: the content types the two fixtures grant on
FIXTURE_MODELS = {"mapcontext", "mapcontextlayer",
                  "webmapservicemonitoringsetting"}


def grants_of(table):
    """The (codename, group, primary key) triples of a dedicated group table"""
    return set(table.objects.values_list(
        "permission__codename", "group__name", "content_object_id"))


def shared_rows():
    """Every row of guardian's shared tables, with the model it grants on.

    A lookup narrows the shared table by ``permission__content_type``, so the
    model whose primary key decides the cast is the one of the *permission* - the
    row's own ``content_type`` is not what a lookup filters on.

    Returns:
        list: tuples of (row, model, name of the actor)
    """
    rows = []
    for perms_model, actor in ((GroupObjectPermission, "group"),
                               (UserObjectPermission, "user")):
        for row in perms_model.objects.select_related(
                "permission__content_type"):
            rows.append(
                (row, row.permission.content_type.model_class(), actor))
    return rows


class FixtureGrantsAnswerFromTheirOwnTables(TestCase):
    """The object permissions the fixtures of this repository write.

    A fixture which loads a row into the shared table does what the code of a
    deployment does: it puts the text of an integer primary key into the column
    every lookup of a uuid primary key may have to cast. Both fixtures grant on a
    model of an integer primary key: the map applications and their layers, and
    the monitoring setting of a web map service.
    """

    fixtures = FIXTURES

    def test_the_map_application_grants_answer_from_its_own_table(self):
        """The map application and its layers are answered from their tables"""
        self.assertEqual(
            grants_of(MapContextGroupObjectPermission), MAPCONTEXT_GRANTS)
        self.assertEqual(
            grants_of(MapContextLayerGroupObjectPermission),
            {("change_mapcontextlayer", "Group2", pk) for pk in GRANTED_LAYERS}
            | {("delete_mapcontextlayer", "Group2", pk)
               for pk in GRANTED_LAYERS})

    def test_the_monitoring_setting_grant_answers_from_its_own_table(self):
        """The schedule of a web map service is a model of an integer key too"""
        self.assertEqual(
            grants_of(WebMapServiceMonitoringSettingGroupObjectPermission),
            {("change_webmapservicemonitoringsetting", "Group1", 1)})

    def test_no_grant_of_a_fixture_lives_in_the_shared_table(self):
        """The shared tables answer nothing of the models with their own table

        An object permission of one of these models in the shared table is both a
        grant nobody reads - guardian answers the model from its own table - and
        the text a lookup of a model with a uuid primary key may have to cast.
        """
        for row, target, actor in shared_rows():
            self.assertNotIn(
                target._meta.model_name, FIXTURE_MODELS,
                f"guardian's {actor} table holds an object permission of "
                f"{target.__name__} (object_pk {row.object_pk!r})")
            perms_model = (get_group_obj_perms_model(target)
                           if actor == "group"
                           else get_user_obj_perms_model(target))
            self.assertTrue(
                perms_model.objects.is_generic(),
                f"the {actor} table holds a permission on {target.__name__} "
                f"while guardian answers that model from "
                f"{perms_model.__name__}")

    def test_every_row_of_the_shared_tables_is_readable_as_a_primary_key(self):
        """The invariant behind the whole issue

        A lookup casts ``object_pk`` to the primary key of the model it was asked
        for. A row whose text that primary key cannot read is the row which
        answers ``invalid input syntax for type uuid`` - so no object permission
        this repository writes may leave one behind.
        """
        for row, target, actor in shared_rows():
            try:
                target._meta.pk.to_python(row.object_pk)
            except Exception as error:
                self.fail(
                    f"the {actor} table holds object_pk {row.object_pk!r} for "
                    f"{target.__name__}, which the primary key of that model "
                    f"cannot read: {error}")

    def test_the_bootstrap_and_a_loaded_deployment_keep_the_invariant(self):
        """What a deployment writes when it runs, stays readable

        An organization created through the ORM is granted to the groups the
        bootstrap creates for it, and ``test_deployed_organization.json`` is the
        dump of such a deployment: the organization, its groups and the grants
        which belong to them. Every one of these primary keys is an integer.
        """
        Organization.objects.create(name="Invariant Organization")
        call_command("loaddata", "test_deployed_organization", verbosity=0)

        self.assertTrue(
            OrganizationGroupObjectPermission.objects.exists(),
            "the bootstrap granted nothing, so this test would assert nothing")
        for row, target, actor in shared_rows():
            try:
                uuid.UUID(row.object_pk)
            except ValueError:
                self.fail(
                    f"the {actor} table holds object_pk {row.object_pk!r} for "
                    f"{target.__name__}: the text of an integer primary key in "
                    f"the shared table is what breaks the lookup of every model "
                    f"with a uuid primary key")


class ServiceLookupsAnswerFromTheirOwnTables(TestCase):
    """The models the reads which scope by permission ask.

    ``collect_service_alerts`` asks every kind of service with a filtered
    queryset, and the visibility of the background activity asks every content
    type a process names as its resource - in both cases the services. An object
    permission of an integer primary key in the table they are answered from is
    the reason they 500, so all three kinds need a table of their own, also the
    catalogue whose permissions no code grants today.

    The assertion reads the export of the package and not a behaviour: a test
    module which imports ``registry.models.guardian`` registers those models for
    the whole run, so a lookup answers from the dedicated table whether or not an
    application which imports only ``registry.models`` would find it.
    """

    def test_the_package_exports_a_table_for_every_kind_of_service(self):
        models = importlib.import_module("registry.models")
        for service in SERVICE_KIND_OF:
            for actor in ("User", "Group"):
                table = f"{service.__name__}{actor}ObjectPermission"
                self.assertTrue(
                    hasattr(models, table),
                    f"registry.models does not export {table}, so an "
                    f"application which imports only the package answers a "
                    f"lookup of {service.__name__} from the shared table")


class AlertsWithTheGrantsOfTheFixturesAnswer(TestCase):
    """The read the issue names, with the grants of these fixtures in place.

    ``/api/registry/service-alerts`` scopes its rows by the services the caller
    may view and asks that per kind of service with a filtered queryset - the
    shape which takes the cast of the shared column, and the one #862
    reproduced the 500 of with the row of an organization. Whether a given read
    really evaluates the cast for the rows of the other models is the plan's
    decision, which is the issue's whole point, so this pins the answer instead
    of an error: the read answers, and a caller without any grant is answered
    with nothing.
    """

    fixtures = FIXTURES

    def setUp(self):
        self.user = get_user_model().objects.get(username="User2")
        client = APIClient()
        client.force_authenticate(self.user)
        # without an explicit accept the browsable api renderer is used
        client.credentials(HTTP_ACCEPT=JSONAPI)
        self.client = client

    def body(self, **query):
        response = self.client.get(
            reverse("registry:service-alert-list"), query)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_the_alerts_of_a_caller_without_any_grant_answer(self):
        refresh_service_alerts()

        self.assertEqual(self.body()["data"], [])

    def test_the_layer_the_fixture_grants_to_the_caller_is_still_its_own(self):
        """The grants moved with the table: the api answers them as before

        The behaviour this pins is the one the scenario
        ``mapcontextlayer/update_mapcontextlayers.feature`` expects: User2 of
        Group2 may change a layer of the second map application and not one of
        the first.
        """
        payload = {
            "data": {
                "type": "MapContextLayer",
                "id": str(GRANTED_LAYER),
                "attributes": {"title": "changed by the group it grants to"},
            }
        }

        granted = self.client.patch(
            f"/api/registry/mapcontextlayers/{GRANTED_LAYER}",
            payload, format="vnd.api+json")
        self.assertEqual(granted.status_code, 200, granted.content)

        other = self.client.patch(
            "/api/registry/mapcontextlayers/1", payload,
            format="vnd.api+json")
        self.assertEqual(other.status_code, 403, other.content)
