from collections.abc import Sequence
from typing import Any, Dict, List
from xml import etree

from camel_converter import to_snake
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models import Exists
from django.db.models import Value as V
from django.db.models.expressions import F, OuterRef
from django.db.models.functions import Coalesce
from django_cte import CTEManager
from extras.managers import DefaultHistoryManager
from mptt2.managers import TreeManager
from mptt2.models import Tree
from registry.enums.metadata import MetadataOriginEnum
from registry.models.metadata import (Dimension, Keyword, LegendUrl,
                                      MetadataContact, MimeType,
                                      ReferenceSystem, Style, TimeExtent,
                                      WebFeatureServiceRemoteMetadata,
                                      WebMapServiceRemoteMetadata)
from registry.querys.service import LayerQuerySet
from registry.settings import METADATA_URL_BLACKLIST
from simple_history.utils import bulk_create_with_history


class TransientObjectsManagerMixin(object):

    _transient_objects = {}

    def _update_transient_objects(self, kv: Dict):
        for key, value in kv.items():
            if isinstance(value, Sequence) and not isinstance(value, str):
                current_value = self._transient_objects.get(key, [])
                current_value.extend(value)
                self._transient_objects.update({key: current_value})
            else:
                self._transient_objects.update({key: value})

    def _persist_transient_objects(self):
        set_attr_key = None
        get_attr_key = None
        for key, value in self._transient_objects.items():
            if "pre_db_job" in key:
                # handle command like "update__style_id__with__style.pk"
                # foreignkey id attribute is not updated after bulk_create is done. So we need to update it manually
                # before we create related objects in bulk.
                # todo: find better way to update foreignkey id
                cmd = value.split("__")
                set_attr_key = cmd[1]
                get_attr_key = cmd[3]
            elif isinstance(value, Sequence) and len(value) > 0:
                if set_attr_key and get_attr_key:
                    for obj in value:
                        # handle pre db job detected by last loop
                        setattr(obj, set_attr_key, getattr(
                            obj, get_attr_key.split(".")[1]))
                    set_attr_key = None
                    get_attr_key = None
                value[0]._meta.model.objects.bulk_create(objs=value)

    def _handle_transient_m2m_objects(self, db_obj: models.Model):
        m2m_fields = [field.name for field in db_obj._meta.local_many_to_many]
        transient_fields = filter(
            lambda key: '__transient' in key, db_obj.__dict__.keys())
        transient_m2m_fields = [
            transient_field for transient_field in transient_fields if any(m2m_field in transient_field for m2m_field in m2m_fields)]

        for key in transient_m2m_fields:
            attr = getattr(db_obj, key.split("__transient_")[1])
            attr.add(*getattr(db_obj, key))

    def get_or_create_list(self, list, model_cls):
        items = []

        for item in list:
            # TODO: slow get_or_create solution - maybe there is a better way to do this
            if isinstance(item, str):
                db_item, _ = model_cls.objects.get_or_create(
                    **{to_snake(model_cls.__name__): item})
            else:
                db_item, _ = model_cls.objects.get_or_create(
                    **item.transform_to_model())
            items.append(db_item)
        return items


class WebMapServiceCapabilitiesManager(TransientObjectsManagerMixin, models.Manager):
    """Manager to create a WebMapService with all related objects by given parsed capabilities."""

    def _create_service_instance(self, parsed_service):
        """ Creates the service instance and all depending/related objects """
        from registry.models.service import (WebMapService,
                                             WebMapServiceOperationUrl)
        parsed_service_contact = parsed_service.service_contact

        db_service_contact, _ = MetadataContact.objects.get_or_create(
            **parsed_service_contact.transform_to_model())

        service: WebMapService = super().create(origin=MetadataOriginEnum.CAPABILITIES.value,
                                                service_contact=db_service_contact,
                                                metadata_contact=db_service_contact,
                                                **parsed_service.transform_to_model())
        # keywords
        keyword_list = self.get_or_create_list(
            list=list(filter(
                lambda k: k != "" and k != None, parsed_service.keywords)),
            model_cls=Keyword)
        service.keywords.add(*keyword_list)
        # xml
        service.xml_backup_file.save(name='capabilities.xml',
                                     content=ContentFile(
                                         str(parsed_service.serializeDocument(), "UTF-8")),
                                     save=False)
        service.save(without_historical=True)

        # operation urls
        operation_urls = []
        for operation_url in parsed_service.operation_urls:
            db_operation_url = WebMapServiceOperationUrl(
                service=service,
                **operation_url.transform_to_model())
            db_operation_url.mime_type_list = []

            mime_type_list = self.get_or_create_list(
                list=operation_url.mime_types,
                model_cls=MimeType)

            db_operation_url.mime_type_list.extend(mime_type_list)
            operation_urls.append(db_operation_url)

        db_operation_url_list = WebMapServiceOperationUrl.objects.bulk_create(
            objs=operation_urls)

        for db_operation_url in db_operation_url_list:
            db_operation_url.mime_types.add(*db_operation_url.mime_type_list)

        return service

    def _construct_remote_metadata_instances(self, parsed_sub_element, db_service, db_sub_element):
        from registry.models.service import Layer
        sub_element_content_type = ContentType.objects.get_for_model(
            model=Layer)
        remote_metadata_list = []
        for remote_metadata in parsed_sub_element.remote_metadata:
            if any(link in remote_metadata.link for link in METADATA_URL_BLACKLIST):
                # skip every remote link which contains any of the string of the blacklist
                continue

            remote_metadata_list.append(WebMapServiceRemoteMetadata(service=db_service,
                                                                    content_type=sub_element_content_type,
                                                                    object_id=db_sub_element.pk,
                                                                    **remote_metadata.transform_to_model()))
        self._update_transient_objects(
            {"remote_metadata_list": remote_metadata_list})

    def _construct_style_instances(self, parsed_layer, db_layer):
        style_list = []
        legend_url_list = []
        for style in parsed_layer.styles:
            db_style = Style(layer=db_layer,
                             **style.transform_to_model())
            if style.legend_url:
                # legend_url is optional for style entities
                db_mime_type, _ = MimeType.objects.get_or_create(
                    mime_type=style.legend_url.mime_type.transform_to_model())
                legend_url_list.append(LegendUrl(style=db_style,
                                                 mime_type=db_mime_type,
                                                 **style.legend_url.transform_to_model()))
            style_list.append(db_style)
        self._update_transient_objects({
            "style_list": style_list,
            "pre_db_job__style_list": "update__style_id__with__style.pk",
            "legend_url_list": legend_url_list
        })

    def _construct_dimension_instances(self, parsed_layer, db_layer):
        dimension_list = []
        time_extent_list = []
        for dimension in parsed_layer.dimensions:
            db_dimension = Dimension(layer=db_layer,
                                     **dimension.transform_to_model())
            dimension_list.append(db_dimension)

            for dimension_extent in dimension.time_extents:
                time_extent_list.append(TimeExtent(dimension=db_dimension,
                                                   **dimension_extent.transform_to_model()))

        self._update_transient_objects({
            "dimension_list": dimension_list,
            "pre_db_job__dimension_list": "update__dimension_id__with__dimension.pk",
            "time_extent_list": time_extent_list
        })

    def _treeify(self, parsed_layer, db_service, tree, db_parent=None, cursor=1, level=0):
        """
        adapted function from
        https://github.com/django-mptt/django-mptt/blob/7a6a54c6d2572a45ea63bd639c25507108fff3e6/mptt/managers.py#L716
        to construct the correct layer tree
        """
        from registry.models.service import Layer
        node = Layer(service=db_service,
                     mptt_parent=db_parent,
                     origin=MetadataOriginEnum.CAPABILITIES.value,

                     **parsed_layer.transform_to_model())

        self._update_transient_objects({"layer_list": [node]})

        node.mptt_tree = tree
        node.mptt_depth = level
        node.mptt_lft = cursor

        node.__transient_keywords = self.get_or_create_list(
            list=list(filter(
                lambda k: k != "" and k != None,  parsed_layer.keywords)),
            model_cls=Keyword
        )

        node.__transient_reference_systems = self.get_or_create_list(
            list=parsed_layer.reference_systems,
            model_cls=ReferenceSystem
        )

        self._construct_remote_metadata_instances(parsed_sub_element=parsed_layer,
                                                  db_service=db_service,
                                                  db_sub_element=node)
        self._construct_style_instances(parsed_layer=parsed_layer,
                                        db_layer=node)
        self._construct_dimension_instances(parsed_layer=parsed_layer,
                                            db_layer=node)

        for child in parsed_layer.children:
            cursor = self._treeify(
                parsed_layer=child,
                db_service=db_service,
                tree=tree,
                db_parent=node,
                cursor=cursor + 1,
                level=level + 1)
        cursor += 1
        node.mptt_rgt = cursor
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
        tree = Tree.objects.create()
        self._treeify(
            parsed_layer=parsed_service.root_layer,
            db_service=db_service,
            tree=tree,
        )

        return tree

    def _create_layer_and_related_objects(self, parsed_service, db_service) -> None:
        from registry.models.service import Layer
        tree = self._construct_layer_tree(
            parsed_service=parsed_service,
            db_service=db_service)

        db_layer_list: List[Layer] = bulk_create_with_history(
            objs=self._transient_objects.pop("layer_list"),
            model=Layer)

        self._persist_transient_objects()

        for db_layer in db_layer_list:
            self._handle_transient_m2m_objects(db_layer)

        # non documented function from mptt to rebuild the tree
        # TODO: check if we need to rebuild if we create the tree with the correct right and left values.
        # moving to mptt2, no partial_rebuild is provided by the package for now
        # Layer.objects.partial_rebuild(tree_id=tree_id)

    def create(self, parsed_service, **kwargs: Any):
        self._transient_objects = {}
        from registry.models.service import WebMapService

        with transaction.atomic():
            db_service: WebMapService = self._create_service_instance(
                parsed_service=parsed_service)
            self._create_layer_and_related_objects(parsed_service=parsed_service,
                                                   db_service=db_service)
        return db_service

    def create_from_capabilities(self, xml_string, service_type, version):
        tree = etree.fromstring(xml_string.encode("utf-8"))
        # mapping holen z. B.
        mapping = XPATH_MAP.get((service_type, version))
        namespaces = mapping.get("_namespaces", {})

        root_xpath = mapping.get("_root", ".")
        root_elem = tree.xpath(root_xpath, namespaces=namespaces)[0]

        parsed = parse_element(
            root_elem, mapping, parent_instance=None, namespaces=namespaces)
        # parsed["layers"] enthält Liste von Layer‑Instanzen
        # parsed["service"] oder andere Felder enthalten einfache Werte
        # dann Modellinstanzen erzeugen / updaten
        service_data = {k: v for k, v in parsed.items() if k != "layers"}
        service = Service.objects.create(**service_data)
        for layer in parsed.get("layers", []):
            # layer ist schon ein Instanz, oder du musst mapping anpassen, je nachdem
            # wenn layer ist dict, konvertiere in Layer-Instanz mit service FK
            if isinstance(layer, dict):
                Layer.objects.create(service=service, **layer)
            else:
                # wenn schon Layer Instanz
                layer.service = service
                layer.save()

        return service

    def with_security_information(self):
        from registry.models.security import AllowedWebMapServiceOperation

        return self.get_queryset().annotate(
            camouflage=Coalesce(
                F("proxy_setting__camouflage"), V(False)),
            log_response=Coalesce(
                F("proxy_setting__log_response"), V(False)),
            is_secured=Exists(
                AllowedWebMapServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                )
            ),
            is_spatial_secured=Exists(
                AllowedWebMapServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                    allowed_area__isnull=False
                )
            )
        )


class WebFeatureServiceCapabilitiesManager(TransientObjectsManagerMixin, models.Manager):
    def _create_service_instance(self, parsed_service):
        """ Creates the service instance and all depending/related objects """
        from registry.models.service import (WebFeatureService,
                                             WebFeatureServiceOperationUrl)
        parsed_service_contact = parsed_service.service_contact

        db_service_contact, created = MetadataContact.objects.get_or_create(
            **parsed_service_contact.transform_to_model())

        service: WebFeatureService = super().create(origin=MetadataOriginEnum.CAPABILITIES.value,
                                                    service_contact=db_service_contact,
                                                    metadata_contact=db_service_contact,

                                                    **parsed_service.transform_to_model())

        # keywords
        keyword_list = self.get_or_create_list(
            list=list(filter(
                lambda k: k != "" and k != None, parsed_service.keywords)),
            model_cls=Keyword)
        service.keywords.add(*keyword_list)
        # xml
        service.xml_backup_file.save(name='capabilities.xml',
                                     content=ContentFile(
                                         str(parsed_service.serializeDocument(), "UTF-8")),
                                     save=False)
        service.save(without_historical=True)

        # operation urls
        operation_urls = []
        for operation_url in parsed_service.operation_urls:
            db_operation_url = WebFeatureServiceOperationUrl(
                service=service,
                **operation_url.transform_to_model())
            db_operation_url.mime_type_list = []

            mime_type_list = self.get_or_create_list(
                list=operation_url.mime_types,
                model_cls=MimeType)

            db_operation_url.mime_type_list.extend(mime_type_list)
            operation_urls.append(db_operation_url)

        db_operation_url_list = WebFeatureServiceOperationUrl.objects.bulk_create(
            objs=operation_urls)

        for db_operation_url in db_operation_url_list:
            db_operation_url.mime_types.add(*db_operation_url.mime_type_list)

        return service

    def _construct_remote_metadata_instances(self, parsed_sub_element, db_service, db_sub_element):
        from registry.models.service import FeatureType
        sub_element_content_type = ContentType.objects.get_for_model(
            model=FeatureType)
        remote_metadata_list = []
        for remote_metadata in parsed_sub_element.remote_metadata:
            if any(link in remote_metadata.link for link in METADATA_URL_BLACKLIST):
                # skip every remote link which contains any of the string of the blacklist
                continue
            remote_metadata_list.append(WebFeatureServiceRemoteMetadata(service=db_service,
                                                                        content_type=sub_element_content_type,
                                                                        object_id=db_sub_element.pk,
                                                                        **remote_metadata.transform_to_model()))
        self._update_transient_objects(
            {"remote_metadata_list": remote_metadata_list})

    def _create_feature_types_and_related_objects(self, parsed_service, db_service):
        db_feature_type_list = []
        from registry.models.service import FeatureType
        for parsed_feature_type in parsed_service.feature_types:
            db_feature_type = FeatureType(service=db_service,
                                          origin=MetadataOriginEnum.CAPABILITIES.value,
                                          **parsed_feature_type.transform_to_model())
            self._update_transient_objects(
                {"feature_type_list": [db_feature_type]})

            db_feature_type.__transient_keywords = self.get_or_create_list(
                list=list(filter(
                    lambda k: k != "" and k != None, parsed_feature_type.keywords)),
                model_cls=Keyword
            )

            db_feature_type.__transient_reference_systems = self.get_or_create_list(
                list=parsed_feature_type.reference_systems,
                model_cls=ReferenceSystem
            )
            db_feature_type.__transient_output_formats = self.get_or_create_list(
                list=parsed_feature_type.output_formats,
                model_cls=MimeType
            )

            self._construct_remote_metadata_instances(parsed_sub_element=parsed_feature_type,
                                                      db_service=db_service,
                                                      db_sub_element=db_feature_type)

        db_feature_type_list: List[FeatureType] = bulk_create_with_history(
            objs=self._transient_objects.pop("feature_type_list"),
            model=FeatureType)

        self._persist_transient_objects()

        for db_feature_type in db_feature_type_list:
            self._handle_transient_m2m_objects(db_feature_type)

    def create(self, parsed_service, **kwargs: Any):
        self._transient_objects = {}
        from registry.models.service import WebFeatureService

        with transaction.atomic():
            db_service: WebFeatureService = self._create_service_instance(
                parsed_service=parsed_service)
            self._create_feature_types_and_related_objects(parsed_service=parsed_service,
                                                           db_service=db_service)
        return db_service

    def with_security_information(self):
        from registry.models.security import AllowedWebFeatureServiceOperation

        return self.get_queryset().annotate(
            camouflage=Coalesce(
                F("proxy_setting__camouflage"), V(False)),
            log_response=Coalesce(
                F("proxy_setting__log_response"), V(False)),
            is_secured=Exists(
                AllowedWebFeatureServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                )
            ),
            is_spatial_secured=Exists(
                AllowedWebFeatureServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                    allowed_area__isnull=False
                )
            )
        )


class CatalogueServiceCapabilitiesManager(TransientObjectsManagerMixin, models.Manager):
    def _create_service_instance(self, parsed_service):
        """ Creates the service instance and all depending/related objects """
        from registry.models.service import (CatalogueService,
                                             CatalogueServiceOperationUrl)

        parsed_service_contact = parsed_service.service_contact

        db_service_contact, created = MetadataContact.objects.get_or_create(
            **parsed_service_contact.transform_to_model())

        service: CatalogueService = super().create(origin=MetadataOriginEnum.CAPABILITIES.value,
                                                   service_contact=db_service_contact,
                                                   metadata_contact=db_service_contact,
                                                   **parsed_service.transform_to_model())
        # keywords
        keyword_list = self.get_or_create_list(
            list=list(filter(
                lambda k: k != "" and k != None, parsed_service.keywords)),
            model_cls=Keyword)
        service.keywords.add(*keyword_list)

        # xml
        service.xml_backup_file.save(name='capabilities.xml',
                                     content=ContentFile(
                                         str(parsed_service.serializeDocument(), "UTF-8")),
                                     save=False)
        service.save(without_historical=True)

        # operation urls
        operation_urls = []
        for operation_url in parsed_service.operation_urls:
            db_operation_url = CatalogueServiceOperationUrl(
                service=service,
                **operation_url.transform_to_model())
            db_operation_url.mime_type_list = []

            mime_type_list = self.get_or_create_list(
                list=operation_url.mime_types,
                model_cls=MimeType)

            db_operation_url.mime_type_list.extend(mime_type_list)
            operation_urls.append(db_operation_url)

        db_operation_url_list = CatalogueServiceOperationUrl.objects.bulk_create(
            objs=operation_urls)

        for db_operation_url in db_operation_url_list:
            db_operation_url.mime_types.add(*db_operation_url.mime_type_list)

        return service

    def create(self, parsed_service):
        with transaction.atomic():
            db_service = self._create_service_instance(
                parsed_service=parsed_service)
        return db_service


class FeatureTypeElementXmlManager(models.Manager):

    def _reset_local_variables(self, **kwargs):
        # bulk_create will not call the default save() of CommonInfo model. So we need to set the attributes manual. We
        # collect them once.
        from simple_history.models import HistoricalRecords

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


class LayerManager(models.Manager.from_queryset(LayerQuerySet), DefaultHistoryManager, TreeManager):
    pass


class CatalogueServiceManager(DefaultHistoryManager, CTEManager):
    pass
