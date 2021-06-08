import os
from celery import states
from django.contrib.auth.hashers import make_password
from model_bakery import seq
from model_bakery.recipe import Recipe, foreign_key
from users.models import MrMapUser
from structure.models import Organization, PublishRequest, Workflow
from tests.test_data import get_password_data


salt = str(os.urandom(25).hex())
PASSWORD = get_password_data().get('valid')
EMAIL = "test@example.com"


god_user = Recipe(
    MrMapUser,
    username="God",
    email="god@heaven.va",
    salt=salt,
    password=make_password("354Dez25!"),
    is_active=True,
)

superadmin_orga = Recipe(
    Organization,
    name=seq("SuperOrganization"),
)


superadmin_user = Recipe(
    MrMapUser,
    username="Superuser",
    email="test@example.com",
    password=make_password(PASSWORD, salt=salt),
    is_active=True,
    #groups=related(superadmin_group),
    is_superuser=True
)

active_testuser = Recipe(
    MrMapUser,
    username="Testuser",
    email="test@example.com",
    password=make_password(PASSWORD, salt=salt),
    is_active=True,
)

inactive_testuser = active_testuser.extend(
    is_active=False,
)

pending_task = Recipe(
    Workflow,
    status=states.STARTED,
    task_id=1
)
