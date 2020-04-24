"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 24.04.20

"""

from django.test import TestCase, RequestFactory, Client

from service.models import Category, Keyword
from tests import utils
from tests.baker_recipes.db_setup import create_keywords, create_categories, create_superadminuser
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD


class EditorAutocompleteTestCase(TestCase):

    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)

        self.request_factory = RequestFactory()
        # Create a bunch of random keywords
        create_keywords(20)
        create_categories(10)

        self.categories = Category.objects.all()
        self.keywords = Keyword.objects.all()

    def test_editor_autocomplete_keyword(self):
        """ Tests editor app autocomplete functionality for Keywords

        Returns:
        """
        return_values = utils.check_autocompletion_response(
            self.keywords,
            "keyword",
            self.client,
            "editor:keyword-autocomplete",
        )
        for item in return_values:
            elem = item["elem"]
            val = item["val"]
            self.assertTrue(val, msg="Editor keyword autocompletion didn't work for '{}'".format(elem))

    def test_editor_autocomplete_category(self):
        """ Tests editor app autocomplete functionality for Keywords

        Returns:
        """
        return_values = utils.check_autocompletion_response(
            self.categories,
            "title_locale_1",
            self.client,
            "editor:category-autocomplete",
        )
        for item in return_values:
            elem = item["elem"]
            val = item["val"]
            self.assertTrue(val, msg="Editor category autocompletion didn't work for '{}'".format(elem))
