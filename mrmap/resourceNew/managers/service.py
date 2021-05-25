from django.db import models, transaction
from django.db.models import Max
from django.contrib.contenttypes.models import ContentType


class ServiceXmlManager(models.Manager):
    """
    handles the creation of objects by using the parsed service which is stored in the given :class:`new.Service`
    instance.
    """
    last_node_level = 0
    parent_lookup = None
    current_parent = None

    db_layer_list = []
    db_layer_metadata_list = []
    db_remote_metadata_list = []
    db_style_list = []
    db_legend_url_list = []

    # to avoid from circular import problems, we lookup the model from the parsed python objects. The model is
    # stored on the parsed python objects in attribute `model`.
    layer_cls = None
    layer_content_type = None
    layer_metadata_cls = None
    keyword_cls = None
    remote_metadata_cls = None
    mime_type_cls = None
    style_cls = None
    legend_url_cls = None

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

    def _update_current_parent(self, parsed_layer):
        # todo: maybe we can move node id setting to get_all_layers()
        if self.last_node_level < parsed_layer.level:
            # Climb down the tree. In this case the last node is always the a parent node. (preorder traversal)
            # We store it in our parent_lookup dict to resolve it if we climb up
            # the tree again. In case of climb up we loose the directly parent.
            self.current_parent = self.db_layer_list[-1]
            self.parent_lookup.update({self.current_parent.node_id: self.current_parent})
            parsed_layer.node_id = self.db_layer_list[-1].node_id + ".1"
        elif self.last_node_level > parsed_layer.level:
            # climb up the tree. We need to lookup the parent of this node.
            sibling_node_id = self.db_layer_list[-1].parent.node_id.split(".")
            sibling_node_id[-1] = str(int(sibling_node_id[-1]) + 1)
            parsed_layer.node_id = ".".join(sibling_node_id)
            self.current_parent = self.parent_lookup.get(parsed_layer.node_id.rsplit(".", 1)[0])
        else:
            # sibling node. we just increase the node_id counter
            if self.parent_lookup:
                last_node_id = self.db_layer_list[-1].node_id.split(".")
                last_node_id[-1] = str(int(last_node_id[-1]) + 1)
                parsed_layer.node_id = ".".join(last_node_id)
            else:
                parsed_layer.node_id = "1"
        self.last_node_level = parsed_layer.level

    def _construct_layer_metadata_instance(self, parsed_layer, db_layer):
        if not self.layer_metadata_cls:
            self.layer_metadata_cls = parsed_layer.layer_metadata.get_model_class()

        db_layer_metadata = self.layer_metadata_cls(described_layer=db_layer,
                                                    **parsed_layer.layer_metadata.get_field_dict())
        db_layer_metadata.keyword_list = []
        self.db_layer_metadata_list.append(db_layer_metadata)

        for keyword in parsed_layer.layer_metadata.keywords:
            # todo: slow get_or_create solution - maybe there is a better way to do this
            if not self.keyword_cls:
                self.keyword_cls = keyword.get_model_class()
            db_keyword, created = self.keyword_cls.objects.get_or_create(**keyword.get_field_dict())
            db_layer_metadata.keyword_list.append(db_keyword)

    def _construct_remote_metadata_instances(self, parsed_layer, db_service, db_layer):
        if not self.layer_content_type:
            self.layer_content_type = ContentType.objects.get_for_model(model=self.layer_cls)
        for remote_metadata in parsed_layer.remote_metadata:
            if not self.remote_metadata_cls:
                self.remote_metadata_cls = remote_metadata.get_model_class()
            self.db_remote_metadata_list.append(self.remote_metadata_cls(service=db_service,
                                                                         content_type=self.layer_content_type,
                                                                         object_id=db_layer.pk,
                                                                         **remote_metadata.get_field_dict()))

    def _construct_style_instances(self, parsed_layer, db_layer):
        for style in parsed_layer.styles:
            if not self.style_cls:
                self.style_cls = style.get_model_class()
            db_style = self.style_cls(layer=db_layer,
                                      **style.get_field_dict())
            if style.legend_url:
                # legend_url is optional for style entities
                if not self.legend_url_cls:
                    self.legend_url_cls = style.legend_url.get_model_class()
                if not self.mime_type_cls:
                    self.mime_type_cls = style.legend_url.mime_type.get_model_class()
                db_mime_type, created = self.mime_type_cls.objects.get_or_create(
                    **style.legend_url.mime_type.get_field_dict())
                self.db_legend_url_list.append(self.legend_url_cls(style=db_style,
                                                                   mime_type=db_mime_type,
                                                                   **style.legend_url.get_field_dict()))
            self.db_style_list.append(db_style)

    def _construct_layer_tree(self, parsed_service, db_service):
        """ traverse all layers of the parsed service with pre order traversing, constructs all related db objects and
            append them to global lists to use bulk create for all objects. Some db models will created instantly.

            keywords and mime types will be created instantly, cause unique constraints are configured on this models.

            Args:
                parsed_service (plain python object): the parsed service in the same hierarchy structure as the
                                                      :class:`resourceNew.models.service.Service`
                db_service (Service): the persisted :class:`resourceNew.models.service.Service`

            Returns:
                tree_id (int): the used tree id of the constructed layer objects.
        """
        for parsed_layer in parsed_service.get_all_layers():
            # Note!!!: the given list must be ordered in preorder cause
            # the following algorithm is written for preorder traversal
            if not self.parent_lookup:
                self.parent_lookup = {}
                self.layer_cls = parsed_layer.get_model_class()
                tree_id = self._get_next_tree_id(self.layer_cls)

            self._update_current_parent(parsed_layer=parsed_layer)

            # to support bulk create for mptt model lft, rght, tree_id can't be None
            db_layer = self.layer_cls(service=db_service,
                                      parent=self.current_parent,
                                      lft=parsed_layer.left,
                                      rght=parsed_layer.right,
                                      tree_id=tree_id,
                                      level=parsed_layer.level,
                                      **parsed_layer.get_field_dict())
            db_layer.node_id = parsed_layer.node_id
            self.db_layer_list.append(db_layer)

            self._construct_layer_metadata_instance(parsed_layer=parsed_layer,
                                                    db_layer=db_layer)
            self._construct_remote_metadata_instances(parsed_layer=parsed_layer,
                                                      db_service=db_service,
                                                      db_layer=db_layer)
            self._construct_style_instances(parsed_layer=parsed_layer,
                                            db_layer=db_layer)

            # todo: append dimension list
        return tree_id

    def create(self, parsed_service, *args, **kwargs):
        """ Custom create function for :class:`models.Service` which is based on the parsed capabilities document.

            Args:
                parsed_service: the parsed Service object based on the :class:`new.Service` class.

            Returns:
                db instance (Service): the created Service object based on the :class:`models.Service`
        """
        with transaction.atomic():
            service = self._create_service_instance(parsed_service=parsed_service, *args, **kwargs)

            tree_id = self._construct_layer_tree(parsed_service=parsed_service, db_service=service)

            self.layer_cls.objects.bulk_create(objs=self.db_layer_list)
            # non documented function from mptt to rebuild the tree
            self.layer_cls.objects.partial_rebuild(tree_id=tree_id)

            self.style_cls.objects.bulk_create(objs=self.db_style_list)

            for legend_url in self.db_legend_url_list:
                # style_id attribute is not updated after bulk_create is done. So we need to update it manually before
                # we create related legend url objects in bulk.
                # todo: find better way to update style_id
                legend_url.style_id = legend_url.style.pk
            self.legend_url_cls.objects.bulk_create(objs=self.db_legend_url_list)

            db_layer_metadata_list = self.layer_metadata_cls.objects.bulk_create(objs=self.db_layer_metadata_list)
            for db_layer_metadata in db_layer_metadata_list:
                db_layer_metadata.keywords.add(*db_layer_metadata.keyword_list)

            self.remote_metadata_cls.objects.bulk_create(objs=self.db_remote_metadata_list)

        return service
