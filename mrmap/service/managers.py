from django.db import models


class ServiceXmlManager(models.Manager):
    """
    handles the creation of objects by using the parsed service which is stored in the given :class:`new.Service`
    instance.
    """

    def create(self, parsed_service, *args, **kwargs):
        """ Custom create function for :class:`models.Service` which is based on the parsed capabilities document.

            Args:
                parsed_service: the parsed Service object based on the :class:`new.Service` class.

            Returns:
                db instance (Service): the created Service object based on the :class:`models.Service`
        """
        db_keywords = []
        for keyword in parsed_service.get_all_keywords():
            db_keyword, created = keyword.get_model_class().objects.get_or_create(**keyword.get_field_dict())
            if created:
                db_keywords.append(db_keyword)

        for mime_type in parsed_service.get_all_mime_types():
            db_mime_type, created = mime_type.get_model_class().objects.get_or_create(**mime_type.get_field_dict())
            mime_type.db_obj = db_mime_type

        layer_metadata_db_objects = []
        for layer_metadata in parsed_service.get_all_layer_metadata():
            layer_metadata_db_objects.append(layer_metadata.get_db_model_instance())
        parsed_service.get_all_layer_metadata()[0].get_model_class().objects.bulk_create(objs=layer_metadata_db_objects)

        for layer_metadata in parsed_service.get_all_layer_metadata():
            db_layer_metadata = layer_metadata.get_db_model_instance()

            db_keywords = [keyword for keyword in db_keywords if keyword.keyword in [keyword.keyword for keyword in layer_metadata.keywords]]

            db_layer_metadata.keywords.add(*db_keywords)

        for layer in parsed_service.get_all_layers():
            db_layer = layer.get_db_model_instance()
            db_layer.metadata = layer.layer_metadata.get_db_model_instance()
            if layer.parent:
                db_layer.parent = layer.parent.get_db_model_instance()

        return super(ServiceXmlManager, self).create(*args, **kwargs)
