"""State setup and assertions of the resource ownership scenarios (#733).

The scenarios POST a registration while celery answers its task in the
scenario's own process (``CELERY_TASK_ALWAYS_EAGER``) and the capabilities
request of that task is served from the test data instead of the network.
That is the one way this suite can assert what the task writes: the
registration task is where the service row - and with it the owner - comes
into the world.
"""
from pathlib import Path
from unittest.mock import patch

from behave import given, then
from django.contrib.auth import get_user_model
from django.test.utils import override_settings

from accounts.models.groups import Organization
from registry.models.service import WebMapService
from tests.django.utils import MockResponse

#: the capabilities document served for a mocked registration: the same
#: document the unit tests of the registration task serve
CAPABILITIES_WMS = Path(__file__).resolve().parents[
    2] / "django/test_data/capabilities/wms/1.3.0.xml"


@given('User1 is member of the organization "{organization_name}"')
def user_joins_organization(context, organization_name):
    """A membership decides which organization may own what User1 registers"""
    user = get_user_model().objects.get(username="User1")
    user.groups.add(Organization.objects.get(name=organization_name))


@given('User1 is also member of a second organization "{organization_name}"')
def user_joins_second_organization(context, organization_name):
    """Two memberships make the ownership question ambiguous on purpose"""
    user = get_user_model().objects.get(username="User1")
    organization = Organization.objects.create(name=organization_name)
    user.groups.add(organization)


@given("the registration task runs directly and serves its capabilities "
       "from the test data")
def registration_runs_directly(context):
    """Celery answers within this scenario, without a worker or network.

    The task's document request reads the WMS capabilities of the unit test
    data; the payload URLs of the scenarios are only what the validator of
    the create endpoint reads.
    """
    overrides = override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        CELERY_TASK_EAGER_PROPAGATES=True,
        BROKER_BACKEND="memory")
    overrides.enable()
    context.add_cleanup(overrides.disable)

    patcher = patch(
        "registry.tasks.service.GuardedSession.send",
        return_value=MockResponse(status_code=200,
                                  content=CAPABILITIES_WMS))
    patcher.start()
    context.patchers.append(patcher)

    # The task_prerun and task_postrun receivers of MrMap.celery close the
    # database connections around every task - worker hygiene around a
    # forked process which does not apply here: in eager mode the task runs
    # in this very process, inside the TestCase's atomic block, where a
    # closed connection may not be reopened. The receivers look the names
    # below up in their module at call time, so patching the names silences
    # the closing while leaving the receivers themselves connected.
    for name in ("MrMap.celery.close_old_connections",
                 "MrMap.celery.connections"):
        patcher = patch(name)
        patcher.start()
        context.patchers.append(patcher)

    # one behave run leaves the fixtures of its features in the database, so
    # the assertions below read this scenario's registrations against the
    # service count which was already there before the POST
    context.wms_count_before = WebMapService.objects.count()


@then("the WMS which this run registered is owned by the organization "
      "\"{organization_name}\"")
def registered_service_is_owned(context, organization_name):
    organization = Organization.objects.get(name=organization_name)
    # the title of the capabilities document which the mocked task request
    # serves: only a registration of this very scenario can carry it
    services = list(WebMapService.objects.filter(title="DWD GeoServer WMS"))
    assert len(services) == 1, (
        "the registration persisted "
        f"{len(services)} services instead of exactly one")
    assert services[0].owner == organization, (
        f"the registered service is owned by {services[0].owner}, "
        f"not by {organization_name}")


@then("no service was registered")
def no_service_registered(context):
    assert WebMapService.objects.count() == context.wms_count_before, (
        "a refused registration may not leave a service behind")
