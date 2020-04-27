"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 27.04.20

"""
from django.test import TestCase, Client

from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service, create_wfs_service
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD


class EditorIndexViewTestCase(TestCase):
    """ Test case for basic index view of WMS and WFS editor

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(self.user.get_groups().first(), 10)
        create_wfs_service(self.user.get_groups().first(), 10)


class EditorWMSIndexViewTestCase(TestCase):
    """ Test case for basic index view of WMS editor

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(self.user.get_groups().first(), 10)


class EditorWFSIndexViewTestCase(TestCase):
    """ Test case for basic index view of WFS editor

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wfs_service(self.user.get_groups().first(), 10)


class EditorMetadataEditViewTestCase(TestCase):
    """ Test case for basic metadata editor view

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(self.user.get_groups().first(), 1)


class EditorAccessEditViewTestCase(TestCase):
    """ Test case for basic access editor view

    """
    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        create_wms_service(self.user.get_groups().first(), 10)
