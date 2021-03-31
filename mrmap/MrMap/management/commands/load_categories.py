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

from MrMap.management.commands.setup_settings import CATEGORIES, CATEGORIES_LANG
from service.helper.common_connector import CommonConnector
from service.helper.enums import CategoryOriginEnum
from service.models import Category


class Command(BaseCommand):
    help = "Loads all categories, declared in the settings.py, into the database."

    def add_arguments(self, parser):
        pass

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Load categories..."))

        for category_src, category_url in CATEGORIES.items():
            # parse english at first, other languages afterwards
            raw_categories = self.get_category_json(category_url, "en")
            self.create_categories_en(raw_categories, category_src)

            for lang_key, lang_val in CATEGORIES_LANG.items():
                raw_categories = self.get_category_json(category_url, lang_val)
                self.update_categories(raw_categories, lang_key, category_src)

    def get_category_json(self, category_url, language):
        """ Loads the json response from a connector class

        Args:
            category_url: The uri where the definitions can be loaded from
            language: The language which shall be fetched
        Returns:
             response (str): The response body content
        """
        uri_lang = category_url.format(language)
        if (CommonConnector().url_is_reachable("https://www.google.de/",10)[0] is not True):
            self.stdout.write(
                self.style.NOTICE("Internet connection test failed! Proxies have to be specified in MrMap/settings.py."))
            self.stdout.write(
                self.style.NOTICE("Setup will be canceled! Please make sure to have a working internet connection!"))
            exit()

        connector = CommonConnector(uri_lang)
        connector.load()
        return connector.content


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
        if origin == CategoryOriginEnum.ISO.value:
            label = "label"
            descr = "definition"
            text = "text"
            link = "id"
        elif origin == CategoryOriginEnum.INSPIRE.value:
            label = "preferredLabel"
            descr = "definition"
            text = "string"
            link = "uri"
        else:
            # For future implementation
            pass

        ret_list = []
        # iterate for another language over all categories and set the correct translated attributes
        items = json.loads(raw_categories.decode("utf-8"))
        if origin == CategoryOriginEnum.ISO.value:
            items = items["metadata-codelist"]["containeditems"]
        for item in items:
            if origin == CategoryOriginEnum.ISO.value:
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
        self.stdout.write(self.style.SUCCESS("Added language '{}' to {} themes.".format(lang_key, origin)))
        return ret_list

    def create_categories_en(self, raw_categories: str, origin):
        """ Create initial category objects by parsing the english version of inspire theme api

        Args:
            raw_categories (str): The raw response body from the API
            origin : The origin object to which these categories belong to
        Returns:
             ret_list (list): Contains all retrieved category objects in english language
        """
        # to make it more maintainable, we only use one function which decides dynamically how the json is accessed
        # based on the parsed type of origin
        if origin == CategoryOriginEnum.ISO.value:
            label = "label"
            descr = "definition"
            text = "text"
            link = "id"
        elif origin == CategoryOriginEnum.INSPIRE.value:
            label = "preferredLabel"
            descr = "definition"
            text = "string"
            link = "uri"
        else:
            # For future implementation
            pass

        ret_list = []
        items = json.loads(raw_categories.decode("utf-8"))
        if origin == CategoryOriginEnum.ISO.value:
            items = items["metadata-codelist"]["containeditems"]
        for item in items:
            if origin == CategoryOriginEnum.ISO.value:
                item = item["value"]
            category = Category.objects.get_or_create(
                type=origin,
                title_EN=item[label][text],
                description_EN=item[descr][text],
                online_link=item[link],
            )
            is_new = category[1]
            category = category[0]
            if is_new:
                # had to be created newly
                category.uuid = uuid.uuid4()
                category.is_active = True
                category.save()
            ret_list.append(category)
        self.stdout.write(self.style.SUCCESS("Created initial english {} themes.".format(origin)))
        return ret_list
