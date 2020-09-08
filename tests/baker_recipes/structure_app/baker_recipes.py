import os
import random

from django.contrib.auth.hashers import make_password
from model_bakery import seq
from model_bakery.recipe import Recipe, foreign_key, related
from structure.models import Organization, PendingTask, PublishRequest
from structure.models import MrMapUser, Theme, Role, MrMapGroup
from structure.settings import SUPERUSER_GROUP_NAME, PUBLIC_GROUP_NAME
from tests.test_data import get_password_data


salt = str(os.urandom(25).hex())
PASSWORD = get_password_data().get('valid')
EMAIL = "test@example.com"


light_theme = Recipe(
    Theme,
    name=seq("LIGHT")
)

superadmin_role = Recipe(
    Role,
    name="superadmin_role",
)

guest_role = Recipe(
    Role,
    name="guest_role",
)


god_user = Recipe(
    MrMapUser,
    username="God",
    email="god@heaven.va",
    salt=salt,
    password=make_password("354Dez25!"),
    is_active=True,
    theme=foreign_key(light_theme),
)

superadmin_orga = Recipe(
    Organization,
    organization_name=seq("SuperOrganization"),
    is_auto_generated=False
)

superadmin_group = Recipe(
    MrMapGroup,
    name=SUPERUSER_GROUP_NAME,
    role=foreign_key(superadmin_role),
    created_by=foreign_key(god_user),
    organization=foreign_key(superadmin_orga)
)

public_group = Recipe(
    MrMapGroup,
    name=PUBLIC_GROUP_NAME,
    description="Public",
    is_public_group=True,
    role=foreign_key(guest_role),
    created_by=foreign_key(god_user),
)

superadmin_user = Recipe(
    MrMapUser,
    username="Superuser",
    email="test@example.com",
    salt=salt,
    password=make_password(PASSWORD, salt=salt),
    is_active=True,
    theme=foreign_key(light_theme),
    groups=related(superadmin_group),
    organization=foreign_key(superadmin_orga)
)

non_autogenerated_orga = Recipe(
    Organization,
    organization_name=seq("RealOrg"),
    is_auto_generated=False,
)

guest_group = Recipe(
    MrMapGroup,
    name=seq("GuestGroup", increment_by=int(random.random() * 100)),
    role=foreign_key(guest_role),
    description=seq("Description"),
    #created_by=foreign_key(god_user),
)

active_testuser = Recipe(
    MrMapUser,
    username="Testuser",
    email="test@example.com",
    salt=salt,
    password=make_password(PASSWORD, salt=salt),
    is_active=True,
    theme=foreign_key(light_theme),
    groups=related(guest_group)
)

inactive_testuser = active_testuser.extend(
    is_active=False,
)

publish_request = Recipe(
    PublishRequest,
    group=foreign_key(superadmin_group),
    organization=foreign_key(non_autogenerated_orga),
)

pending_task = Recipe(
    PendingTask,
    description='{"description": "test task", "phase": "ERROR"}',
    task_id=1
)
