from abc import abstractmethod
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models import Max
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from extras.models import get_current_owner
from registry.enums.metadata import MetadataOrigin
from crum import get_current_user


class ServiceCapabilitiesManager(models.Manager):
    """
    handles the creation of objects by using the parsed service which is stored in the given :class:`new.Service`
    instance.
    """
    db_remote_metadata_list = []
    db_dimension_list = []

    # to avoid from circular import problems, we lookup the model from the parsed python objects. The model is
    # stored on the parsed python objects in attribute `model`.
    sub_element_cls = None
    sub_element_content_type = None
    service_metadata_cls = None
    keyword_cls = None
    remote_metadata_cls = None
    mime_type_cls = None

    dimension_cls = None
    reference_system_cls = None

    common_info = {}

    def _reset_local_variables(self):
        """helper function to reset local variables.
           It seems to be that a manager in django is a singleton object.
        """

        self.db_sub_element_metadata_list = []
        self.db_remote_metadata_list = []

        self.db_dimension_list = []
        self.db_dimension_extent_list = []

        self.sub_element_cls = None
        self.sub_element_content_type = None
        self.sub_element_metadata_cls = None
        self.service_metadata_cls = None
        self.keyword_cls = None
        self.remote_metadata_cls = None
        self.mime_type_cls = None

        self.dimension_cls = None
        self.dimension_extent_cls = None
        self.reference_system_cls = None

        # bulk_create will not call the default save() of CommonInfo model. So we need to set the attributes manual. We
        # collect them once.
        now = timezone.now()
        current_user = get_current_user()
        self.common_info = {"created_at": now,
                            "last_modified_at": now,
                            "last_modified_by": current_user,
                            "created_by_user": current_user,
                            "owned_by_org": get_current_owner(),
                            }

    def _get_or_create_keywords(self, parsed_keywords, db_object):
        db_object.keyword_list = []
        for keyword in parsed_keywords:
            # todo: slow get_or_create solution - maybe there is a better way to do this
            if not self.keyword_cls:
                self.keyword_cls = keyword.get_model_class()
            db_keyword, created = self.keyword_cls.objects.get_or_create(**keyword.get_field_dict())
            db_object.keyword_list.append(db_keyword)

    def _create_service_instance(self, parsed_service, *args, **kwargs):
        """ Creates the service instance and all depending/related objects """
        # create service instance first

        parsed_service_contact = parsed_service.service_metadata.service_contact
        service_contact_cls = parsed_service_contact.get_model_class()
        db_service_contact, created = service_contact_cls.objects.get_or_create(**parsed_service_contact.get_field_dict())

        service = super().create(origin=MetadataOrigin.CAPABILITIES.value,
                                 service_contact=db_service_contact,
                                 metadata_contact=db_service_contact,
                                 *args,
                                 **kwargs,
                                 **parsed_service.get_field_dict(),
                                 **parsed_service.service_metadata.get_field_dict())

        self._get_or_create_keywords(parsed_keywords=parsed_service.service_metadata.keywords,
                                     db_object=service)

        # m2m objects
        service.keywords.add(*service.keyword_list)

        service.xml_backup_file.save(name='capabilities.xml',
                                     content=ContentFile(str(parsed_service.serializeDocument(), "UTF-8")))

        operation_urls = []
        operation_url_model_cls = None
        for operation_url in parsed_service.operation_urls:
            if not operation_url_model_cls:
                operation_url_model_cls = operation_url.get_model_class()
            db_operation_url = operation_url_model_cls(service=service,
                                                       **self.common_info,
                                                       **operation_url.get_field_dict())
            db_operation_url.mime_type_list = []

            if operation_url.mime_types:
                for mime_type in operation_url.mime_types:
                    # todo: slow get_or_create solution - maybe there is a better way to do this
                    if not self.mime_type_cls:
                        self.mime_type_cls = mime_type.get_model_class()
                    db_mime_type, created = self.mime_type_cls.objects.get_or_create(**mime_type.get_field_dict())
                    db_operation_url.mime_type_list.append(db_mime_type)
            operation_urls.append(db_operation_url)
        db_operation_url_list = operation_url_model_cls.objects.bulk_create(objs=operation_urls)

        for db_operation_url in db_operation_url_list:
            db_operation_url.mime_types.add(*db_operation_url.mime_type_list)

        return service

    def _construct_remote_metadata_instances(self, parsed_sub_element, db_service, db_sub_element):
        if not self.sub_element_content_type:
            self.sub_element_content_type = ContentType.objects.get_for_model(model=self.sub_element_cls)
        for remote_metadata in parsed_sub_element.remote_metadata:
            if not self.remote_metadata_cls:
                self.remote_metadata_cls = remote_metadata.get_model_class()
            self.db_remote_metadata_list.append(self.remote_metadata_cls(service=db_service,
                                                                         content_type=self.sub_element_content_type,
                                                                         object_id=db_sub_element.pk,
                                                                         **self.common_info,
                                                                         **remote_metadata.get_field_dict()))

    def _get_or_create_output_formats(self, parsed_feature_type, db_feature_type):
        for mime_type in parsed_feature_type.output_formats:
            # todo: slow get_or_create solution - maybe there is a better way to do this
            if not self.mime_type_cls:
                self.mime_type_cls = mime_type.get_model_class()
            db_mime_type, created = self.mime_type_cls.objects.get_or_create(**mime_type.get_field_dict())
            db_feature_type.db_output_format_list.append(db_mime_type)

    def _construct_dimension_instances(self, parsed_layer, db_layer):

        for dimension in parsed_layer.dimensions:
            if not self.dimension_cls:
                self.dimension_cls = dimension.get_model_class()
            db_dimension = self.dimension_cls(layer=db_layer,
                                              **self.common_info,
                                              **dimension.get_field_dict())
            self.db_dimension_list.append(db_dimension)
            dimension.parse_extent()
            for dimension_extent in dimension.extents:
                if not self.dimension_extent_cls:
                    self.dimension_extent_cls = dimension_extent.get_model_class()
                self.db_dimension_extent_list.append(self.dimension_extent_cls(dimension=db_dimension,
                                                     **self.common_info,
                                                     **dimension_extent.get_field_dict()))

    def _create_reference_system_instances(self, parsed_sub_element, db_sub_element):
        db_sub_element.reference_system_list = []
        for reference_system in parsed_sub_element.reference_systems:
            # todo: slow get_or_create solution - maybe there is a better way to do this
            if not self.reference_system_cls:
                self.reference_system_cls = reference_system.get_model_class()
            db_reference_system, created = self.reference_system_cls.objects.get_or_create(**reference_system.get_field_dict())
            db_sub_element.reference_system_list.append(db_reference_system)

    @abstractmethod
    def create_from_parsed_service(self, parsed_service, *args, **kwargs):
        """ Custom create function for :class:`models.Service` which is based on the parsed capabilities document.

            Args:
                parsed_service: the parsed Service object based on the :class:`new.Service` class.

            Returns:
                db instance (Service): the created Service object based on the :class:`models.Service`
        """
        raise NotImplementedError


class WebMapServiceCapabilitiesManager(ServiceCapabilitiesManager):
    last_node_level = 0
    parent_lookup = None
    current_parent = None

    db_layer_list = []
    db_style_list = []
    db_legend_url_list = []
    style_cls = None
    legend_url_cls = None

    def _reset_local_variables(self):
        super._reset_local_variables()
        self.last_node_level = 0
        self.parent_lookup = None
        self.current_parent = None

        self.db_layer_list = []
        self.db_style_list = []
        self.db_legend_url_list = []

        self.style_cls = None
        self.legend_url_cls = None

    def _get_next_tree_id(self, layer_cls):
        max_tree_id = layer_cls.objects.filter(parent=None).aggregate(Max('tree_id'))
        tree_id = max_tree_id.get("tree_id__max")
        if isinstance(tree_id, int):
            tree_id += 1
        else:
            tree_id = 0
        return tree_id

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

    def _construct_style_instances(self, parsed_layer, db_layer):
        for style in parsed_layer.styles:
            if not self.style_cls:
                self.style_cls = style.get_model_class()
            db_style = self.style_cls(layer=db_layer,
                                      **self.common_info,
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
                                                                   **self.common_info,
                                                                   **style.legend_url.get_field_dict()))
            self.db_style_list.append(db_style)

    def _construct_layer_tree(self, parsed_service, db_service):
        """ traverse all layers of the parsed service with pre order traversing, constructs all related db objects and
            append them to global lists to use bulk create for all objects. Some db models will created instantly.

            keywords and mime types will be created instantly, cause unique constraints are configured on this models.

            Args:
                parsed_service (plain python object): the parsed service in the same hierarchy structure as the
                                                      :class:`registry.models.service.Service`
                db_service (Service): the persisted :class:`registry.models.service.Service`

            Returns:
                tree_id (int): the used tree id of the constructed layer objects.
        """
        if not self.parent_lookup:
            self.parent_lookup = {}

        if not self.sub_element_cls:
            self.sub_element_cls = parsed_service.get_all_layers()[0].get_model_class()

        tree_id = self._get_next_tree_id(self.sub_element_cls)

        for parsed_layer in parsed_service.get_all_layers():
            # Note!!!: the given list must be ordered in preorder cause
            # the following algorithm is written for preorder traversal
            self._update_current_parent(parsed_layer=parsed_layer)

            # to support bulk create for mptt model lft, rght, tree_id can't be None
            # todo: add commoninfo attributes like created_at, last_modified_by, created_by_user, owned_by_org
            db_layer = self.sub_element_cls(service=db_service,
                                            parent=self.current_parent,
                                            lft=parsed_layer.left,
                                            rght=parsed_layer.right,
                                            tree_id=tree_id,
                                            level=parsed_layer.level,
                                            origin=MetadataOrigin.CAPABILITIES.value,
                                            **self.common_info,
                                            **parsed_layer.get_field_dict(),
                                            **parsed_layer.metadata.get_field_dict())
            db_layer.node_id = parsed_layer.node_id
            self.db_layer_list.append(db_layer)
            self._get_or_create_keywords(parsed_keywords=parsed_layer.metadata.keywords,
                                         db_object=db_layer)

            self._construct_remote_metadata_instances(parsed_sub_element=parsed_layer,
                                                      db_service=db_service,
                                                      db_sub_element=db_layer)
            self._construct_style_instances(parsed_layer=parsed_layer,
                                            db_layer=db_layer)
            self._construct_dimension_instances(parsed_layer=parsed_layer,
                                                db_layer=db_layer)

            self._create_reference_system_instances(parsed_sub_element=parsed_layer,
                                                    db_sub_element=db_layer)
        return tree_id

    def _create_wms(self, parsed_service, db_service):
        tree_id = self._construct_layer_tree(parsed_service=parsed_service, db_service=db_service)

        db_layer_list = self.sub_element_cls.objects.bulk_create(objs=self.db_layer_list)
        # non documented function from mptt to rebuild the tree
        # todo: check if we need to rebuild if we create the tree with the correct right and left values.
        self.sub_element_cls.objects.partial_rebuild(tree_id=tree_id)

        # ForeingKey objects
        if self.db_style_list:
            self.style_cls.objects.bulk_create(objs=self.db_style_list)
        if self.db_legend_url_list:
            for legend_url in self.db_legend_url_list:
                # foreignkey id attribute is not updated after bulk_create is done. So we need to update it manually
                # before we create related objects in bulk.
                # todo: find better way to update foreignkey id
                legend_url.style_id = legend_url.style.pk
            self.legend_url_cls.objects.bulk_create(objs=self.db_legend_url_list)
        if self.db_dimension_list:
            self.dimension_cls.objects.bulk_create(objs=self.db_dimension_list)
        if self.db_dimension_extent_list:
            for db_dimension_extent in self.db_dimension_extent_list:
                # foreignkey id attribute is not updated after bulk_create is done. So we need to update it manually
                # before we create related objects in bulk.
                # todo: find better way to update foreignkey id
                db_dimension_extent.dimension_id = db_dimension_extent.dimension.pk
            self.dimension_extent_cls.objects.bulk_create(objs=self.db_dimension_extent_list)
        if self.db_remote_metadata_list:
            self.remote_metadata_cls.objects.bulk_create(objs=self.db_remote_metadata_list)

        for db_layer in db_layer_list:
            db_layer.keywords.add(*db_layer.keyword_list)
            db_layer.reference_systems.add(*db_layer.reference_system_list)

    def create_from_parsed_service(self, parsed_service, *args, **kwargs):
        self._reset_local_variables()
        with transaction.atomic():
            db_service = self._create_service_instance(parsed_service=parsed_service, *args, **kwargs)
            self._create_wms(parsed_service=parsed_service, db_service=db_service)
        return db_service


class WebFeatureServiceCapabilitiesManager(ServiceCapabilitiesManager):

    def _create_wfs(self, parsed_service, db_service):
        db_feature_type_list = []
        if not self.sub_element_cls:
            self.sub_element_cls = parsed_service.feature_types[0].get_model_class()
        for parsed_feature_type in parsed_service.feature_types:
            db_feature_type = self.sub_element_cls(service=db_service,
                                                   origin=MetadataOrigin.CAPABILITIES.value,
                                                   **self.common_info,
                                                   **parsed_feature_type.get_field_dict(),
                                                   **parsed_feature_type.metadata.get_field_dict())
            db_feature_type.db_output_format_list = []
            db_feature_type_list.append(db_feature_type)
            self._get_or_create_keywords(parsed_keywords=parsed_feature_type.metadata.keywords,
                                         db_object=db_feature_type)

            self._construct_remote_metadata_instances(parsed_sub_element=parsed_feature_type,
                                                      db_service=db_service,
                                                      db_sub_element=db_feature_type)
            # todo:
            """
            self._construct_dimension_instances(parsed_layer=parsed_layer,
                                                db_layer=db_layer)
            """
            self._get_or_create_output_formats(parsed_feature_type=parsed_feature_type, db_feature_type=db_feature_type)
            self._create_reference_system_instances(parsed_sub_element=parsed_feature_type,
                                                    db_sub_element=db_feature_type)

        db_feature_type_list = self.sub_element_cls.objects.bulk_create(objs=db_feature_type_list)

        if self.db_remote_metadata_list:
            self.remote_metadata_cls.objects.bulk_create(objs=self.db_remote_metadata_list)

        for db_feature_type in db_feature_type_list:
            db_feature_type.keywords.add(*db_feature_type.keyword_list)
            db_feature_type.output_formats.add(*db_feature_type.db_output_format_list)
            db_feature_type.reference_systems.add(*db_feature_type.reference_system_list)

    def create_from_parsed_service(self, parsed_service, *args, **kwargs):
        self._reset_local_variables()
        with transaction.atomic():
            db_service = self._create_service_instance(parsed_service=parsed_service, *args, **kwargs)
            self._create_wfs(parsed_service=parsed_service, db_service=db_service)
        return db_service


class CatalougeServiceCapabilitiesManager(ServiceCapabilitiesManager):
    def create_from_parsed_service(self, parsed_service, *args, **kwargs):
        self._reset_local_variables()
        with transaction.atomic():
            db_service = self._create_service_instance(parsed_service=parsed_service, *args, **kwargs)
        return db_service


class FeatureTypeElementXmlManager(models.Manager):
    common_info = {}

    def _reset_local_variables(self):
        # bulk_create will not call the default save() of CommonInfo model. So we need to set the attributes manual. We
        # collect them once.
        now = timezone.now()
        current_user = get_current_user()
        self.common_info = {"created_at": now,
                            "last_modified_at": now,
                            "last_modified_by": current_user,
                            "created_by_user": current_user,
                            "owned_by_org": get_current_owner(),
                            }

    def create_from_parsed_xml(self, parsed_xml, related_object):
        self._reset_local_variables()

        db_element_list = []
        for element in parsed_xml.elements:
            db_element_list.append(self.model(feature_type=related_object,
                                              **self.common_info,
                                              **element.get_field_dict()))
        return self.model.objects.bulk_create(objs=db_element_list)
