from django.db import models, transaction
from django.db.models import Max
from django.contrib.contenttypes.models import ContentType


class ServiceXmlManager(models.Manager):
    """
    handles the creation of objects by using the parsed service which is stored in the given :class:`new.Service`
    instance.
    """

    def _get_next_tree_id(self, layer_cls):
        max_tree_id = layer_cls.objects.filter(parent=None).aggregate(Max('tree_id'))
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

    def _create_layer_metadata(self, xml_layer, db_layer):
        db_layer_metadata = xml_layer.layer_metadata.get_model_class()(described_layer=db_layer,
                                                                       **xml_layer.get_field_dict())
        return db_layer_metadata

    def _create_layer_tree(self, parsed_service, service):
        # create layer instances
        db_layer_list = []
        db_layer_metadata_list = []
        db_remote_metadata_list = []
        db_keyword_list = []
        layer_content_type = None
        parent_lookup = None
        current_parent = None
        last_node_level = 0

        # to avoid from circular import problems, we lookup the model from the parsed python objects. The model is
        # stored on the parsed python objects in attribute `model`.
        layer_cls = None
        layer_metadata_cls = None
        keyword_cls = None
        remote_metadata_cls = None

        for parsed_layer in parsed_service.get_all_layers():
            # Note!!!: the given list must be ordered in preorder cause
            # the following algorithm is written for preorder traversal
            if not parent_lookup:
                parent_lookup = {}

                layer_cls = parsed_layer.get_model_class()
                layer_content_type = ContentType.objects.get_for_model(model=layer_cls)

                tree_id = self._get_next_tree_id(layer_cls)

            # todo: maybe we can move node id setting to get_all_layers()
            if last_node_level < parsed_layer.level:
                # Climb down the tree. In this case the last node is always the a parent node. (preorder traversal)
                # We store it in our parent_lookup dict to resolve it if we climb up
                # the tree again. In case of climb up we loose the directly parent.
                current_parent = db_layer_list[-1]
                parent_lookup.update({current_parent.node_id: current_parent})
                parsed_layer.node_id = db_layer_list[-1].node_id + ".1"
            elif last_node_level > parsed_layer.level:
                # climb up the tree. We need to lookup the parent of this node.
                sibling_node_id = db_layer_list[-1].parent.node_id.split(".")
                sibling_node_id[-1] = str(int(sibling_node_id[-1]) + 1)
                parsed_layer.node_id = ".".join(sibling_node_id)
                current_parent = parent_lookup.get(parsed_layer.node_id.rsplit(".", 1)[0])
            else:
                # sibling node. we just increase the node_id counter
                if parent_lookup:
                    last_node_id = db_layer_list[-1].node_id.split(".")
                    last_node_id[-1] = str(int(last_node_id[-1]) + 1)
                    parsed_layer.node_id = ".".join(last_node_id)
                else:
                    parsed_layer.node_id = "1"

            last_node_level = parsed_layer.level
            # to support bulk create for mptt model lft, rght, tree_id can't be None
            db_layer = layer_cls(service=service,
                                 parent=current_parent,
                                 lft=parsed_layer.left,
                                 rght=parsed_layer.right,
                                 tree_id=tree_id,
                                 level=parsed_layer.level,
                                 **parsed_layer.get_field_dict())
            db_layer.node_id = parsed_layer.node_id
            db_layer_list.append(db_layer)

            if not layer_metadata_cls:
                layer_metadata_cls = parsed_layer.layer_metadata.get_model_class()

            db_layer_metadata = layer_metadata_cls(described_layer=db_layer,
                                                   **parsed_layer.layer_metadata.get_field_dict())
            db_layer_metadata.keyword_list = []
            db_layer_metadata_list.append(db_layer_metadata)

            for keyword in parsed_layer.layer_metadata.keywords:
                if not keyword_cls:
                    keyword_cls = keyword.get_model_class()
                db_keyword = keyword_cls(**keyword.get_field_dict())
                try:
                    exists = next(kw for kw in db_keyword_list if kw.keyword == db_keyword.keyword)
                    db_layer_metadata.keyword_list.append(exists)
                except StopIteration:
                    db_keyword_list.append(db_keyword)
                    db_layer_metadata.keyword_list.append(db_keyword)

            for remote_metadata in parsed_layer.remote_metadata:
                if not remote_metadata_cls:
                    remote_metadata_cls = remote_metadata.get_model_class()
                db_remote_metadata_list.append(remote_metadata_cls(service=service,
                                                                   content_type=layer_content_type,
                                                                   object_id=db_layer.pk,
                                                                   **remote_metadata.get_field_dict()))

            # todo: append styles list
            # todo: append dimension list
        layer_cls.objects.bulk_create(objs=db_layer_list)
        # non documented function from mptt to rebuild the tree
        layer_cls.objects.partial_rebuild(tree_id=tree_id)

        keyword_cls.objects.bulk_create(objs=db_keyword_list)

        db_layer_metadata_list = layer_metadata_cls.objects.bulk_create(objs=db_layer_metadata_list)
        for db_layer_metadata in db_layer_metadata_list:
            db_layer_metadata.keywords.add(*db_layer_metadata.keyword_list)

        remote_metadata_cls.objects.bulk_create(objs=db_remote_metadata_list)

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
