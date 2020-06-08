"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 12.06.19

"""
import json
import uuid

from django.core.management import BaseCommand
from django.db import transaction

from MrMap.settings import CATEGORIES, CATEGORIES_LANG
from service.helper.common_connector import CommonConnector
from service.models import Category, CategoryOrigin


class Command(BaseCommand):
    help = "Loads all categories, declared in the settings.py, into the database."

    def add_arguments(self, parser):
        pass

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Load categories..."))

        # check category origins
        origins = self.check_category_origins()

        for origin in origins:
            # parse english at first, the other languages afterwards
            raw_categories = self.get_category_json(origin, "en")
            self.create_categories_en(raw_categories, origin)
            for lang_key, lang_val in CATEGORIES_LANG.items():
                raw_categories = self.get_category_json(origin, lang_val)
                self.update_categories(raw_categories, lang_key, origin)

    def get_category_json(self, origin, language):
        """ Loads the json response from a connector class

        Args:
            origin: The category origin object which holds the required uri
            language: The language which shall be fetched
        Returns:
             response (str): The response body content
        """
        uri_lang = origin.uri.format(language)
        connector = CommonConnector(uri_lang)
        connector.load()
        return connector.content

    def check_category_origins(self):
        """ Checks if the category origins exist and creates them if not.

        Returns:
             ret_list (list): Contains all category origin objects
        """
        ret_list = []
        for origins_key, origins_val in CATEGORIES.items():
            if isinstance(origins_val, list):
                for val in origins_val:
                    origin = CategoryOrigin.objects.get_or_create(
                        name=origins_key,
                        uri=val
                    )[0]
                    ret_list.append(origin)
            else:
                origin = CategoryOrigin.objects.get_or_create(
                    name=origins_key,
                    uri=origins_val
                )[0]
                ret_list.append(origin)
        return ret_list

    def update_categories(self, raw_categories: str, lang_key, origin):
        """ Updates the languages for the previously created categories.

        Args:
            raw_categories (str): The raw response body from the API
            lang_key: The key identifier from the CATEGORIES_LANG to specifiy which attribute must be filled
        Returns:
             ret_list (list): Contains the category objects with updated languages
        """
        # to make it more maintainable, we only use one function which decides dynamically how the json is accessed
        # based on the parsed type of origin
        if origin.name == "iso":
            label = "label"
            descr = "definition"
            text = "text"
            link = "id"
        else:
            label = "preferredLabel"
            descr = "definition"
            text = "string"
            link = "uri"

        ret_list = []
        # iterate for another language over all categories and set the correct translated attributes
        items = json.loads(raw_categories.decode("utf-8"))
        if origin.name == "iso":
            items = items["metadata-codelist"]["containeditems"]
        for item in items:
            if origin.name == "iso":
                item = item["value"]
            category = Category.objects.get(online_link=item[link])
            if lang_key == "locale_1":
                # not set yet, we are correct in here
                category.title_locale_1 = item[label][text]
                category.description_locale_1 = item[descr][text]
            elif lang_key == "locale_2":
                # not set yet, we are correct in here
                category.title_locale_2 = item[label][text]
                category.description_locale_2 = item[descr][text]
            else:
                pass
            category.save()
            ret_list.append(category)
        self.stdout.write(self.style.SUCCESS("Added language '{}' to {} themes.".format(lang_key, origin.name)))
        return ret_list

    def create_categories_en(self, raw_categories: str, origin: CategoryOrigin):
        """ Create initial category objects by parsing the english version of inspire theme api

        Args:
            raw_categories (str): The raw response body from the API
            origin (CategoryOrigin): The origin object to which these categories belong to
        Returns:
             ret_list (list): Contains all retrieved category objects in english language
        """
        # to make it more maintainable, we only use one function which decides dynamically how the json is accessed
        # based on the parsed type of origin
        if origin.name == "iso":
            label = "label"
            descr = "definition"
            text = "text"
            link = "id"
        else:
            label = "preferredLabel"
            descr = "definition"
            text = "string"
            link = "uri"

        ret_list = []
        items = json.loads(raw_categories.decode("utf-8"))
        if origin.name == "iso":
            items = items["metadata-codelist"]["containeditems"]
        for item in items:
            if origin.name == "iso":
                item = item["value"]
            category = Category.objects.get_or_create(
                type=origin.name,
                title_EN=item[label][text],
                description_EN=item[descr][text],
                online_link=item[link],
                origin=origin
            )
            is_new = category[1]
            category = category[0]
            if is_new:
                # had to be created newly
                category.uuid = uuid.uuid4()
                category.is_active = True
                category.save()
            ret_list.append(category)
        self.stdout.write(self.style.SUCCESS("Created initial english {} themes.".format(origin.name)))
        return ret_list
