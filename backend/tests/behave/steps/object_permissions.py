"""Domain steps of the object permission scenarios below ``features/json:api/auth/``.

The pattern is the one ``steps/manual_updates.py`` sets: ``Given`` steps create
the rows and grants a scenario asserts upon, ``Then`` steps read the database.
The users are deliberately not the fixture users: ``User1`` and ``User2`` sit
in the ``Default-Permissions`` group of ``test_users.json``, which holds the
global change permission for every registry model, so a scenario about *this*
service's object permissions needs a user without that head start. The fixture
rows of a feature are loaded once per feature and not restored, so the
scenarios that edit a service revert their own row change.
"""
from behave import given, then
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from guardian.shortcuts import assign_perm
from registry.models import WebMapService

#: the first WMS of ``test_wms.json``, same service ``manual_updates.py`` uses
SERVICE_ID = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"

#: the title that fixture row carries, which the change scenarios put back
FIXTURE_TITLE = "WMS1"


@given('a user "{username}" without any service permissions exists')
def create_unprivileged_user(context, username):
    user_model = get_user_model()
    user, _ = user_model.objects.get_or_create(username=username)
    user.set_password(username)
    # not a member of Default-Permissions - that group is what a scenario is
    # about to hand out or withhold, explicitly
    user.groups.clear()
    user.save()


@given('the user "{username}" is member of a group granted the WMS')
def grant_wms_object_permission_to_group(context, username):
    user = get_user_model().objects.get(username=username)
    granted, _ = Group.objects.get_or_create(name="Granted WMS Admins")
    user.groups.add(granted)
    assign_perm("registry.change_webmapservice", granted,
                WebMapService.objects.get(pk=SERVICE_ID))


@given('the user "{username}" holds the global permission to change services')
def grant_global_change_permission(context, username):
    user = get_user_model().objects.get(username=username)
    # without an object this is the global grant, exactly what the
    # Default-Permissions group of the fixture carries for every user
    assign_perm("registry.change_webmapservice", user)


@then('the WMS title in the database is "{title}"')
def wms_title_is(context, title):
    assert WebMapService.objects.get(pk=SERVICE_ID).title == title


@then('the WMS title change is reverted')
def revert_wms_title(context):
    # update() rather than save(): neither the model save nor a history row is
    # the behaviour under test, and the next scenario of this feature should
    # find the fixture row as loaddata wrote it
    WebMapService.objects.filter(pk=SERVICE_ID).update(title=FIXTURE_TITLE)
