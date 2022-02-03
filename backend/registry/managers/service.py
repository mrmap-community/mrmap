from abc import abstractmethod
from random import randrange

from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models import Max
from extras.managers import DefaultHistoryManager
from mptt.managers import TreeManager
from registry.enums.metadata import MetadataOrigin
from registry.enums.service import HttpMethodEnum
from simple_history.models import HistoricalRecords
from simple_history.utils import bulk_create_with_history


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

    current_user = None

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
        if hasattr(HistoricalRecords.context, "request") and hasattr(HistoricalRecords.context.request, "user"):
            self.current_user = HistoricalRecords.context.request.user

    def _get_or_create_keywords(self, parsed_keywords, db_object):
        db_object.keyword_list = []
        for keyword in parsed_keywords:
            # todo: slow get_or_create solution - maybe there is a better way to do this
            if not self.keyword_cls:
                self.keyword_cls = keyword.get_model_class()
            db_keyword, created = self.keyword_cls.objects.get_or_create(
                **keyword.get_field_dict())
            db_object.keyword_list.append(db_keyword)

    def _create_service_instance(self, parsed_service):
        """ Creates the service instance and all depending/related objects """
        # create service instance first

        parsed_service_contact = parsed_service.service_metadata.service_contact
        service_contact_cls = parsed_service_contact.get_model_class()
        db_service_contact, created = service_contact_cls.objects.get_or_create(
            **parsed_service_contact.get_field_dict())

        service = self.create(origin=MetadataOrigin.CAPABILITIES.value,
                              service_contact=db_service_contact,
                              metadata_contact=db_service_contact,
                              **parsed_service.get_field_dict(),
                              **parsed_service.service_metadata.get_field_dict())

        self._get_or_create_keywords(parsed_keywords=parsed_service.service_metadata.keywords,
                                     db_object=service)

        # m2m objects
        service.keywords.add(*service.keyword_list)

        service.xml_backup_file.save(name='capabilities.xml',
                                     content=ContentFile(
                                         str(parsed_service.serializeDocument(), "UTF-8")),
                                     save=False)
        service.save(without_historical=True)

        operation_urls = []
        operation_url_model_cls = None
        db_queryables = []
        queryable_model_cls = None
        for operation_url in parsed_service.operation_urls:
            if not operation_url_model_cls:
                operation_url_model_cls = operation_url.get_model_class()

            db_operation_url = operation_url_model_cls(service=service,
                                                       **operation_url.get_field_dict())
            db_operation_url.mime_type_list = []

            if operation_url.mime_types:
                for mime_type in operation_url.mime_types:
                    # todo: slow get_or_create solution - maybe there is a better way to do this
                    if not self.mime_type_cls:
                        self.mime_type_cls = mime_type.get_model_class()
                    db_mime_type, created = self.mime_type_cls.objects.get_or_create(
                        **mime_type.get_field_dict())
                    db_operation_url.mime_type_list.append(db_mime_type)

            if hasattr(operation_url, "queryables") and operation_url.queryables:
                for queryable in operation_url.queryables:
                    if not queryable_model_cls:
                        queryable_model_cls = queryable.get_model_class()
                    db_queryables.append(queryable_model_cls(
                        operation_url=db_operation_url, **queryable.get_field_dict()))

            operation_urls.append(db_operation_url)
        db_operation_url_list = operation_url_model_cls.objects.bulk_create(
            objs=operation_urls)
        if queryable_model_cls and db_queryables:
            queryable_model_cls.objects.bulk_create(objs=db_queryables)

        for db_operation_url in db_operation_url_list:
            db_operation_url.mime_types.add(*db_operation_url.mime_type_list)

        return service

    def _construct_remote_metadata_instances(self, parsed_sub_element, db_service, db_sub_element):
        if not self.sub_element_content_type:
            self.sub_element_content_type = ContentType.objects.get_for_model(
                model=self.sub_element_cls)
        for remote_metadata in parsed_sub_element.remote_metadata:
            if not self.remote_metadata_cls:
                self.remote_metadata_cls = remote_metadata.get_model_class()
            self.db_remote_metadata_list.append(self.remote_metadata_cls(service=db_service,
                                                                         content_type=self.sub_element_content_type,
                                                                         object_id=db_sub_element.pk,
                                                                         **remote_metadata.get_field_dict()))

    def _get_or_create_output_formats(self, parsed_feature_type, db_feature_type):
        for mime_type in parsed_feature_type.output_formats:
            # todo: slow get_or_create solution - maybe there is a better way to do this
            if not self.mime_type_cls:
                self.mime_type_cls = mime_type.get_model_class()
            db_mime_type, created = self.mime_type_cls.objects.get_or_create(
                **mime_type.get_field_dict())
            db_feature_type.db_output_format_list.append(db_mime_type)

    def _construct_dimension_instances(self, parsed_layer, db_layer):

        for dimension in parsed_layer.dimensions:
            if not self.dimension_cls:
                self.dimension_cls = dimension.get_model_class()
            db_dimension = self.dimension_cls(layer=db_layer,
                                              **dimension.get_field_dict())
            self.db_dimension_list.append(db_dimension)
            dimension.parse_extent()
            for dimension_extent in dimension.extents:
                if not self.dimension_extent_cls:
                    self.dimension_extent_cls = dimension_extent.get_model_class()
                self.db_dimension_extent_list.append(self.dimension_extent_cls(dimension=db_dimension,
                                                     **dimension_extent.get_field_dict()))

    def _create_reference_system_instances(self, parsed_sub_element, db_sub_element):
        db_sub_element.reference_system_list = []
        for reference_system in parsed_sub_element.reference_systems:
            # todo: slow get_or_create solution - maybe there is a better way to do this
            if not self.reference_system_cls:
                self.reference_system_cls = reference_system.get_model_class()
            db_reference_system, created = self.reference_system_cls.objects.get_or_create(
                **reference_system.get_field_dict())
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

    layer_opts = None
    db_layer_list = []
    db_style_list = []
    db_legend_url_list = []
    style_cls = None
    legend_url_cls = None

    def _reset_local_variables(self, **kwargs):
        super()._reset_local_variables(**kwargs)
        self.last_node_level = 0
        self.parent_lookup = None
        self.current_parent = None

        self.db_layer_list = []
        self.db_style_list = []
        self.db_legend_url_list = []

        self.style_cls = None
        self.legend_url_cls = None

    def _get_next_tree_id(self, layer_cls):

        max_tree_id = layer_cls.objects.filter(
            parent=None).aggregate(Max('tree_id'))
        tree_id = max_tree_id.get("tree_id__max")
        if isinstance(tree_id, int):
            tree_id += 1
        else:
            tree_id = 0
        # FIXME: not thread safe handling of tree_id... random is only a workaround
        random = randrange(1, 20)
        return tree_id + random

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

    def _treeify(self, parsed_layer, db_service, tree_id, db_parent=None, cursor=1, level=0):
        """
        adapted function from
        https://github.com/django-mptt/django-mptt/blob/7a6a54c6d2572a45ea63bd639c25507108fff3e6/mptt/managers.py#L716
        to construct the correct layer tree
        """

        node = self.sub_element_cls(service=db_service,
                                    parent=db_parent,
                                    origin=MetadataOrigin.CAPABILITIES.value,
                                    **parsed_layer.get_field_dict(),
                                    **parsed_layer.metadata.get_field_dict())

        self.db_layer_list.append(node)

        setattr(node, self.layer_opts.tree_id_attr, tree_id)
        setattr(node, self.layer_opts.level_attr, level)
        setattr(node, self.layer_opts.left_attr, cursor)

        self._get_or_create_keywords(parsed_keywords=parsed_layer.metadata.keywords,
                                     db_object=node)
        self._construct_remote_metadata_instances(parsed_sub_element=parsed_layer,
                                                  db_service=db_service,
                                                  db_sub_element=node)
        self._construct_style_instances(parsed_layer=parsed_layer,
                                        db_layer=node)
        self._construct_dimension_instances(parsed_layer=parsed_layer,
                                            db_layer=node)
        self._create_reference_system_instances(parsed_sub_element=parsed_layer,
                                                db_sub_element=node)

        for child in parsed_layer.children:
            cursor = self._treeify(
                parsed_layer=child,
                db_service=db_service,
                tree_id=tree_id,
                db_parent=node,
                cursor=cursor + 1,
                level=level + 1)
        cursor += 1
        setattr(node, self.layer_opts.right_attr, cursor)
        return cursor

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
            self.sub_element_cls = parsed_service.root_layer.get_model_class()
            self.layer_opts = self.sub_element_cls._mptt_meta

        tree_id = self._get_next_tree_id(self.sub_element_cls)
        self._treeify(
            parsed_layer=parsed_service.root_layer,
            db_service=db_service,
            tree_id=tree_id,
        )

        return tree_id

    def _create_wms(self, parsed_service, db_service):
        tree_id = self._construct_layer_tree(
            parsed_service=parsed_service, db_service=db_service)

        db_layer_list = bulk_create_with_history(
            objs=self.db_layer_list, model=self.sub_element_cls)

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
            self.legend_url_cls.objects.bulk_create(
                objs=self.db_legend_url_list)
        if self.db_dimension_list:
            self.dimension_cls.objects.bulk_create(objs=self.db_dimension_list)
        if self.db_dimension_extent_list:
            for db_dimension_extent in self.db_dimension_extent_list:
                # foreignkey id attribute is not updated after bulk_create is done. So we need to update it manually
                # before we create related objects in bulk.
                # todo: find better way to update foreignkey id
                db_dimension_extent.dimension_id = db_dimension_extent.dimension.pk
            self.dimension_extent_cls.objects.bulk_create(
                objs=self.db_dimension_extent_list)
        if self.db_remote_metadata_list:
            self.remote_metadata_cls.objects.bulk_create(
                objs=self.db_remote_metadata_list)

        for db_layer in db_layer_list:
            db_layer.keywords.add(*db_layer.keyword_list)
            db_layer.reference_systems.add(*db_layer.reference_system_list)

    def create_from_parsed_service(self, parsed_service):
        self._reset_local_variables()
        with transaction.atomic():
            db_service = self._create_service_instance(
                parsed_service=parsed_service)
            self._create_wms(parsed_service=parsed_service,
                             db_service=db_service)
        return db_service


class WebFeatureServiceCapabilitiesManager(ServiceCapabilitiesManager):

    def _create_wfs(self, parsed_service, db_service):
        db_feature_type_list = []
        if not self.sub_element_cls:
            self.sub_element_cls = parsed_service.feature_types[0].get_model_class(
            )
        for parsed_feature_type in parsed_service.feature_types:
            db_feature_type = self.sub_element_cls(service=db_service,
                                                   origin=MetadataOrigin.CAPABILITIES.value,
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
            self._get_or_create_output_formats(
                parsed_feature_type=parsed_feature_type, db_feature_type=db_feature_type)
            self._create_reference_system_instances(parsed_sub_element=parsed_feature_type,
                                                    db_sub_element=db_feature_type)

        db_feature_type_list = bulk_create_with_history(
            objs=db_feature_type_list, model=self.sub_element_cls)

        if self.db_remote_metadata_list:
            self.remote_metadata_cls.objects.bulk_create(
                objs=self.db_remote_metadata_list)

        for db_feature_type in db_feature_type_list:
            db_feature_type.keywords.add(*db_feature_type.keyword_list)
            db_feature_type.output_formats.add(
                *db_feature_type.db_output_format_list)
            db_feature_type.reference_systems.add(
                *db_feature_type.reference_system_list)

    def create_from_parsed_service(self, parsed_service):
        self._reset_local_variables()
        with transaction.atomic():
            db_service = self._create_service_instance(
                parsed_service=parsed_service)
            self._create_wfs(parsed_service=parsed_service,
                             db_service=db_service)
        return db_service


class CatalougeServiceCapabilitiesManager(ServiceCapabilitiesManager):
    def create_from_parsed_service(self, parsed_service):
        self._reset_local_variables()
        with transaction.atomic():
            db_service = self._create_service_instance(
                parsed_service=parsed_service)
        return db_service


class FeatureTypeElementXmlManager(models.Manager):

    def _reset_local_variables(self, **kwargs):
        # bulk_create will not call the default save() of CommonInfo model. So we need to set the attributes manual. We
        # collect them once.
        if hasattr(HistoricalRecords.context, "request") and hasattr(HistoricalRecords.context.request, "user"):
            self.current_user = HistoricalRecords.context.request.user

    def create_from_parsed_xml(self, parsed_xml, related_object, *args, **kwargs):
        self._reset_local_variables(**kwargs)

        db_element_list = []
        for element in parsed_xml.elements:
            db_element_list.append(self.model(feature_type=related_object,
                                              *args,
                                              **element.get_field_dict()))
        return self.model.objects.bulk_create(objs=db_element_list)


class LayerManager(DefaultHistoryManager, TreeManager):

    pass


class CswOperationUrlQueryableQuerySet(models.QuerySet):

    def closest_matches(self, value: str, operation: str, service_id):
        return self.filter(
            value__iendswith=value,
            operation_url__operation=operation,
            operation_url__service__pk=service_id)
