from django.test import TestCase, Client

from service.helper import service_helper
from service.helper.enums import ServiceEnum, VersionEnum
from structure.models import User, Group, Role, Permission

class ServiceTestCase(TestCase):
    """ PLEASE NOTE:

    To run these tests, you have to run the celery worker background process!

    """

    def setUp(self):
        """ Initial creation of objects that are needed during the tests

        Returns:

        """
        # create superuser
        self.perm = Permission()
        self.perm.name = "_default_"
        for key, val in self.perm.__dict__.items():
            if not isinstance(val, bool) and 'can_' not in key:
                continue
            setattr(self.perm, key, True)
        self.perm.save()

        role = Role.objects.create(
            name="Testrole",
            permission=self.perm,
        )

        self.user = User.objects.create(
            username="Testuser",
            is_active=True,
        )

        self.group = Group.objects.create(
            name="Testgroup",
            role=role,
            created_by=self.user,
        )

        self.user.groups.add(self.group)

        self.test_wms = {
            "title": "Karte RP",
            "version": VersionEnum.V_1_1_1,
            "type": ServiceEnum.WMS,
            "uri": "https://www.geoportal.rlp.de/mapbender/php/mod_showMetadata.php/../wms.php?layer_id=38925&PHPSESSID=7qiruaoul2pdcadcohs7doeu07&REQUEST=GetCapabilities&VERSION=1.1.1&SERVICE=WMS&withChilds=1",
        }

        self.test_wfs = {
            "title": "Nutzung",
            "version": VersionEnum.V_1_0_0,
            "type": ServiceEnum.WFS,
            "uri": "https://www.geoportal.rlp.de/mapbender/php/mod_showMetadata.php/../wfs.php?FEATURETYPE_ID=2672&PHPSESSID=7qiruaoul2pdcadcohs7doeu07&REQUEST=GetCapabilities&VERSION=1.1.0&SERVICE=WFS",
        }

    def _get_logged_in_client(self, user: User):
        """ Helping function to encapsulate the login process

        Returns:
             client (Client): The client object, which holds an active session for the user
             user_id (int): The user (id) who shall be logged in
        """
        client = Client()
        user = User.objects.get(
            id=user.id
        )
        self.assertEqual(user.logged_in, False, msg="User already logged in")
        response = client.post("/", data={"username": user.username, "password": self.pw})
        user.refresh_from_db()
        self.assertEqual(response.url, "/home", msg="Redirect wrong")
        self.assertEqual(user.logged_in, True, msg="User not logged in")
        return client

    def test_new_service(self):

        service = service_helper.get_service_model_instance(
            self.test_wms["type"],
            self.test_wms["version"],
            self.test_wms["uri"],
            self.user,
            self.group
        )
        service = service.get("service", None)
        raw_data = service.get("raw_data", None)