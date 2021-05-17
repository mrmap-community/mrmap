from django.contrib.gis.db import models
from serializer.ogc.parser.new import Service as XmlService
from service.models import Keyword


class ServiceXmlManager(models.Manager):
    """
    handles the creation of objects by using the parsed service which is stored in the given :class:`new.Service`
    instance.
    """

    def create(self, parsed_service: XmlService, *args, **kwargs):
        """ Custom create function for :class:`models.Service` which is based on the parsed capabilities document.

            Args:
                parsed_service (XmlService): the parsed Service object based on the :class:`new.Service` class.

            Returns:
                db instance (Service): the created Service object based on the :class:`models.Service`
        """

        Keyword.xml_manager.bulk_create(objs=parsed_service.get_all_keywords())

        return super(ServiceXmlManager, self).create(*args, **kwargs)


class KeywordXmlManger(models.Manager):
    def bulk_create(self, objs, batch_size=None, ignore_conflicts=False):
        """ Overwrites the default bulk_create by adding get_or_create feature.

            Only Keywords which are not persistent jet, will be created by this function in default bulk_create way.
        """

        unique_keywords = []

        for keyword in objs:
            if keyword in unique_keywords:
                unique_keyword = next(_keyword for _keyword in unique_keywords if _keyword.keyword == keyword.keyword)
                keyword.db_obj = unique_keyword.db_obj
            else:
                keyword.get_db_model_instance()  # is stored in keyword.db_obj
                unique_keywords.append(keyword)

        _unique_keywords = [keyword.keyword for keyword in unique_keywords]

        existing_keywords = Keyword.objects.filter(keyword__in=_unique_keywords)

        non_existing_keywords = [keyword for keyword in existing_keywords if keyword.keyword not in _unique_keywords]

        _objs = super().bulk_create(objs=non_existing_keywords, batch_size=batch_size, ignore_conflicts=ignore_conflicts)

        all_keywords = _objs + [kw for kw in existing_keywords]

        return all_keywords
