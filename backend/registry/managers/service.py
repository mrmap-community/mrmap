from collections.abc import Sequence
from typing import Dict

from camel_converter import to_snake
from django.db.models import Exists, Model, Prefetch, QuerySet
from django.db.models import Value as V
from django.db.models.expressions import F, OuterRef
from django.db.models.functions import Coalesce
from django.db.models.manager import Manager
from django_cte import CTEManager
from extras.managers import DefaultHistoryManager
from mptt2.managers import TreeManager
from simple_history.models import HistoricalRecords
from registry import models
from registry.querys.service import LayerQuerySet


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

    def _handle_transient_m2m_objects(self, db_obj: Model):
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


class WebMapServiceQuerySet(QuerySet):
    def prefetch_related_objects(self) -> "WebMapServiceQuerySet":
        styles = Prefetch("styles", queryset=models.Style.objects.select_related("legend_url__mime_type"))
        layers = Prefetch(
            "layers",
            queryset=models.Layer.objects.prefetch_related("keywords", "reference_systems", "time_extents", styles),
        )
        return self.select_related("service_contact", "metadata_contact").prefetch_related(
            "operation_urls", "keywords", layers
        )

    def with_security_information(self) -> "WebMapServiceQuerySet":
        return self.annotate(
            camouflage=Coalesce(
                F("proxy_setting__camouflage"), V(False)),
            log_response=Coalesce(
                F("proxy_setting__log_response"), V(False)),
            is_secured=Exists(
                models.AllowedWebMapServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                )
            ),
            is_spatial_secured=Exists(
                models.AllowedWebMapServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                    allowed_area__isnull=False
                )
            )
        )


class WebFeatureServiceQuerySet(QuerySet):
    def prefetch_related_objects(self) -> "WebFeatureServiceQuerySet":
        featuretypes = Prefetch(
            "featuretypes",
            queryset=models.FeatureType.objects.prefetch_related("keywords", "output_formats", "reference_systems"),
        )
        return self.select_related("service_contact", "metadata_contact").prefetch_related(
            "operation_urls__mime_types", "keywords", featuretypes
        )

    def with_security_information(self) -> "WebFeatureServiceQuerySet":
        return self.annotate(
            camouflage=Coalesce(
                F("proxy_setting__camouflage"), V(False)),
            log_response=Coalesce(
                F("proxy_setting__log_response"), V(False)),
            is_secured=Exists(
                models.AllowedWebFeatureServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                )
            ),
            is_spatial_secured=Exists(
                models.AllowedWebFeatureServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                    allowed_area__isnull=False
                )
            )
        )


class CatalogueServiceQuerySet(QuerySet):
    def prefetch_related_objects(self) -> "CatalogueServiceQuerySet":
        return self.select_related("service_contact", "metadata_contact").prefetch_related(
            "operation_urls__mime_types", "keywords"
        )


class CatalogueServiceManager(DefaultHistoryManager, CTEManager):
    def get_queryset(self) -> CatalogueServiceQuerySet:
        return CatalogueServiceQuerySet(model=self.model, using=self._db)

    def prefetch_related_objects(self) -> CatalogueServiceQuerySet:
        return self.get_queryset().prefetch_related_objects()


class FeatureTypeElementXmlManager(Manager):

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


class LayerManager(Manager.from_queryset(LayerQuerySet), DefaultHistoryManager, TreeManager):
    pass
