import sys
from io import StringIO, UnsupportedOperation

from accounts.models.users import User
from django.contrib.auth.models import Group
from django.core.management import BaseCommand, call_command
from django.db import transaction
from django.db.utils import IntegrityError
from guardian.shortcuts import assign_perm
from model_bakery import baker


class FixtureBuilder(object):

    def build_users_and_groups(self):
        self.user1 = User.objects.create_user(
            username='User1',
            password='User1')
        self.user2 = User.objects.create_user(
            username='User2',
            password='User2')

        self.group1 = Group.objects.create(name='group1')
        self.group2 = Group.objects.create(name='group2')

        self.user1.groups.add(self.group1)
        self.user2.groups.add(self.group2)

    def build_map_contexts(self):
        self.map_context1 = baker.make(
            'registry.MapContext')
        node1 = baker.make(
            'registry.MapContextLayer',
            map_context=self.map_context1)
        node1_1 = baker.make(
            'registry.MapContextLayer',
            map_context=self.map_context1,
            parent=node1)
        node1_1_1 = baker.make(
            'registry.MapContextLayer',
            map_context=self.map_context1,
            parent=node1_1)
        node2 = baker.make(
            'registry.MapContextLayer',
            map_context=self.map_context1)
        node2_1 = baker.make(
            'registry.MapContextLayer',
            map_context=self.map_context1,
            parent=node2)

    def build_mapcontext_fixture(self):
        with transaction.atomic():
            self.build_users_and_groups()
            self.build_map_contexts()

            assign_perm(perm='registry.view_mapcontext',
                        user_or_group=self.group1,
                        obj=self.map_context1)
            assign_perm(perm='registry.change_mapcontext',
                        user_or_group=self.group1,
                        obj=self.map_context1)
            assign_perm(perm='registry.delete_mapcontext',
                        user_or_group=self.group1,
                        obj=self.map_context1)
            call_command(
                'dumpdata',
                '--natural-foreign',
                '--natural-primary',
                'registry',
                'accounts',
                output='./fixture.json')

            raise IntegrityError(
                'Just to force a rollback to dismiss all data from the database.')


class Command(BaseCommand):
    help = "(DEV COMMAND) creates a fixture file for the served scenario"

    def add_arguments(self, parser):
        parser.add_argument(
            'scenario',
            type=str,
            help='the scenario you want to build')

    def handle(self, *args, **options):
        scenario = options["scenario"]
        fb = FixtureBuilder()
        if hasattr(fb, scenario):
            build_func = getattr(fb, scenario)
            build_func()

        else:
            raise UnsupportedOperation('the requested scenario is unknown')
