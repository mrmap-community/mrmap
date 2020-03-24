import os
from django.contrib.auth.hashers import make_password
from structure.models import Theme, MrMapUser, MrMapGroup
from django.utils import timezone
from model_bakery import baker


def create_theme(name: str):
    # creates theme object
    obj, created = Theme.objects.get_or_create(
        name=name
    )
    return obj


def create_active_user(username: str, password: str, email: str):
    # creates user object in db
    salt = str(os.urandom(25).hex())
    obj, created = MrMapUser.objects.get_or_create(
        username=username,
        email=email,
        salt=salt,
        password=make_password(password, salt=salt),
        confirmed_dsgvo=timezone.now(),
        is_active=True,
        theme=create_theme('LIGHT')
    )
    return obj


def create_random_user():
    return baker.make('structure.user',
                      make_m2m=True)


def create_random_users(how_much: int = 1):
    baker.make('structure.user',
               _quantity=how_much,
               make_m2m=True)


def create_random_metatada_with_specific_servicetype_and_group(servicetype_name: str, group: MrMapGroup, ):
    baker.make('service.metadata',
               make_m2m=True,
               service__servicetype__name=servicetype_name,
               created_by=group)


def create_random_metatadas_with_specific_servicetype_and_group(servicetype_name: str, group: MrMapGroup, how_much: int = 1, ):
    baker.make('service.metadata',
               _quantity=how_much,
               make_m2m=True,
               service__servicetype__name=servicetype_name,
               created_by=group)
