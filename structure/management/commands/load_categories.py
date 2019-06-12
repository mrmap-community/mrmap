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
from django.utils import timezone

from MapSkinner.settings import CATEGORIES, CATEGORIES_LANG
from service.helper.common_connector import CommonConnector
from service.models import Category, CategoryOrigin


class Command(BaseCommand):
    help = "Loads all categories, declared in the settings.py, into the database."

    def add_arguments(self, parser):
        pass

    @transaction.atomic
    def handle(self, *args, **options):

        # load uris
        iso_uri = CATEGORIES.get("iso")
        inspire_uri = CATEGORIES.get("inspire")
        additional_uris = CATEGORIES.get("additional")

        # load languages
        languages = []
        for lang_key, lang_val in CATEGORIES_LANG.items():
            if lang_val is not None:
                languages.append(lang_val)

        # check category origins
        origins = self.check_category_origins()

        for origin in origins:
            # parse english at first, the other languages afterwards
            raw_categories = self.get_category_json(origin, "en")
            if origin.name == "iso":
                # ToDo: Implement this!
                pass
            elif origin.name == "inspire":
                categories = self.create_categories_inspire_en(raw_categories, origin)
                for lang in languages:
                    raw_categories = self.get_category_json(origin, lang)
                    categories = self.update_categories_inspire(raw_categories)
            else:
                # ToDo: Implement this somehow generic!
                pass

    def get_category_json(self, origin, language):
        uri_lang = origin.uri.format(language)
        connector = CommonConnector(uri_lang)
        connector.load()
        return connector.text

    def check_category_origins(self):
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


    def update_categories_inspire(self, raw_categories: str):
        ret_list = []
        # iterate for another language over all categories and set the correct translated attributes
        items = json.loads(raw_categories)
        for item in items:
            category = Category.objects.get(online_link=item["uri"])
            if category.title_locale_1 is None:
                # not set yet, we are correct in here
                category.title_locale_1 = item["preferredLabel"]["string"]
                category.description_locale_1 = item["definition"]["string"]
            elif category.title_locale_2 is None:
                # not set yet, we are correct in here
                category.title_locale_2 = item["preferredLabel"]["string"]
                category.description_locale_2 = item["definition"]["string"]
            else:
                pass
            category.save()
            ret_list.append(category)
        return ret_list


    def create_categories_inspire_en(self, raw_categories: str, origin: CategoryOrigin):
        ret_list = []
        items = json.loads(raw_categories)
        #items = cat_dict.get("register", {}).get("containeditems", [])
        for item in items:
            category = Category.objects.get_or_create(
                type=origin.name,
                title_EN=item["preferredLabel"]["string"],
                description_EN=item["definition"]["string"],
                online_link=item["uri"],
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
        return ret_list