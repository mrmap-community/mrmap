from django.db import models, transaction


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
        with transaction.atomic():
            # create service instance first
            service_type, created = parsed_service.service_type.get_model_class().objects.get_or_create(
                                                                        **parsed_service.service_type.get_field_dict())
            service = super().create(service_type=service_type, *args, **kwargs)

            operation_urls = []
            operation_url_model_cls = None
            for operation_url in parsed_service.operation_urls:
                if not operation_url_model_cls:
                    operation_url_model_cls = operation_url.get_model_class()
                operation_urls.append(operation_url_model_cls(service=service, **operation_url.get_field_dict()))
            operation_url_model_cls.objects.bulk_create(objs=operation_urls)

            # create layer instances
            layers = []
            styles = []
            layer_metadata = []
            remote_metadata = []
            layer_model_cls = None
            parent = {0: None}

            for layer in parsed_service.get_all_layers():
                if not layer_model_cls:
                    layer_model_cls = layer.get_model_class()

                # to support bulk create for mptt model we lft, rght, tree_id can't be None
                # todo: check if tree_id=0 is not a default first id value from mptt
                new_layer = layer_model_cls(service=service,
                                            parent=parent.get(layer.level),
                                            lft=0,
                                            rght=0,
                                            tree_id=0,
                                            level=0,
                                            **layer.get_field_dict())
                layers.append(new_layer)

                try:
                    parent.get(layer.level)
                except KeyError:
                    parent[layer.level] = new_layer

                # todo: append styles list
                # todo: append layer metadata
                # todo: append remote metadata list
            layer_model_cls.objects.bulk_create(objs=layers)
            # layer_model_cls.objects.partial_rebuild(tree_id=0)  # non documented function from mptt to rebuild the tree

        """
        # metadata stuff
        db_keywords = []
        for keyword in parsed_service.get_all_keywords():
            db_keyword, created = keyword.get_model_class().objects.get_or_create(**keyword.get_field_dict())
            if created:
                db_keywords.append(db_keyword)

        for mime_type in parsed_service.get_all_mime_types():
            db_mime_type, created = mime_type.get_model_class().objects.get_or_create(**mime_type.get_field_dict())
            mime_type.db_obj = db_mime_type

        for layer in parsed_service.get_all_layers():
            db_layer = layer.get_db_model_instance()
            if layer.parent:
                db_layer.parent = layer.parent.get_db_model_instance()

        
        layer_metadata_db_objects = []
        for layer_metadata in parsed_service.get_all_layer_metadata():
            layer_metadata_db_objects.append(layer_metadata.get_db_model_instance())
        parsed_service.get_all_layer_metadata()[0].get_model_class().objects.bulk_create(objs=layer_metadata_db_objects)

        for layer_metadata in parsed_service.get_all_layer_metadata():
            db_layer_metadata = layer_metadata.get_db_model_instance()

            db_keywords = [keyword for keyword in db_keywords if
                           keyword.keyword in [keyword.keyword for keyword in layer_metadata.keywords]]

            db_layer_metadata.keywords.add(*db_keywords)
        """
        return service
