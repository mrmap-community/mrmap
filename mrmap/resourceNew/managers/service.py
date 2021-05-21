from django.db import models, transaction
from django.db.models import Max


class ServiceXmlManager(models.Manager):
    """
    handles the creation of objects by using the parsed service which is stored in the given :class:`new.Service`
    instance.
    """

    def _get_next_tree_id(self, layer_model_cls):
        max_tree_id = layer_model_cls.objects.filter(parent=None).aggregate(Max('tree_id'))
        tree_id = max_tree_id.get("tree_id__max")
        if isinstance(tree_id, int):
            tree_id += 1
        else:
            tree_id = 0
        return tree_id

    def _create_service_instance(self, parsed_service, *args, **kwargs):
        """ Creates the service instance and all depending/related objects """
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
        return service

    def _create_layer_tree(self, parsed_service, service):
        # create layer instances
        layers = []
        styles = []
        layer_metadata = []
        remote_metadata = []
        layer_model_cls = None
        parent_lookup = {}
        current_parent = None
        last_node_level = 0

        for layer in parsed_service.get_all_layers():
            if not layer_model_cls:
                layer_model_cls = layer.get_model_class()
                tree_id = self._get_next_tree_id(layer_model_cls=layer_model_cls)

            if last_node_level < layer.level:
                current_parent = layers[-1]
                parent_lookup.update({current_parent.node_id: current_parent})
                layer.node_id = layers[-1].node_id + ".1"
            elif last_node_level > layer.level:
                sibling_node_id = layers[-1].parent.node_id.split(".")
                sibling_node_id[-1] = str(int(last_node_id[-1]) + 1)
                layer.node_id = ".".join(sibling_node_id)
                current_parent = parent_lookup.get(layer.node_id.rsplit(".", 1)[0])
            else:
                if parent_lookup:
                    last_node_id = layers[-1].node_id.split(".")
                    last_node_id[-1] = str(int(last_node_id[-1]) + 1)
                    layer.node_id = ".".join(last_node_id)
                else:
                    layer.node_id = "1"

            last_node_level = layer.level
            # to support bulk create for mptt model lft, rght, tree_id can't be None
            new_layer = layer_model_cls(service=service,
                                        parent=current_parent,
                                        lft=layer.left,
                                        rght=layer.right,
                                        tree_id=tree_id,
                                        level=layer.level,
                                        **layer.get_field_dict())
            new_layer.node_id = layer.node_id
            layers.append(new_layer)

            # todo: append styles list
            # todo: append layer metadata
            # todo: append remote metadata list
        layer_model_cls.objects.bulk_create(objs=layers)
        # non documented function from mptt to rebuild the tree
        layer_model_cls.objects.partial_rebuild(tree_id=tree_id)

    def create(self, parsed_service, *args, **kwargs):
        """ Custom create function for :class:`models.Service` which is based on the parsed capabilities document.

            Args:
                parsed_service: the parsed Service object based on the :class:`new.Service` class.

            Returns:
                db instance (Service): the created Service object based on the :class:`models.Service`
        """
        with transaction.atomic():
            service = self._create_service_instance(parsed_service=parsed_service, *args, **kwargs)

            self._create_layer_tree(parsed_service=parsed_service, service=service)

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
