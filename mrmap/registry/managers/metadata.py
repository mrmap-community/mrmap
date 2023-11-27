from datetime import date, datetime
from logging import Logger

from django.conf import settings
from django.contrib.gis.db.models.fields import MultiPolygonField
from django.contrib.postgres.expressions import ArraySubquery
from django.core.exceptions import MultipleObjectsReturned
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models.expressions import Case, F, OuterRef, Value, When
from django.db.models.fields import CharField
from django.db.models.functions import Cast, Coalesce, Concat
from django.db.models.query_utils import Q
from django.utils import timezone
from registry.enums.metadata import MetadataOriginEnum
from registry.exceptions.metadata import UnknownMetadataKind
from simple_history.models import HistoricalRecords

logger: Logger = settings.ROOT_LOGGER


class MetadataRelationManager(models.Manager):

    def for_search(self):
        from registry.models.metadata import Keyword

        # there is a filter used.
        # We need to annotate filterable fields.
        # But we only add annotation for needed fields.
        # So if the filter condition does not lookup for hierarchy_level for example, we don't need to add it to the queryset.
        # TODO: implement a default order by created at
        # add order to get reproduceable query results
        qs = self.get_queryset().order_by("pk")

        qs = qs.annotate(
            hierarchy_level=Case(
                When(dataset_metadata__isnull=False,
                     then=Value("dataset"),
                     ),
                When(service_metadata__isnull=False,
                     then=Value("service"),
                     ),
                default=Value("dataset"),
                output_field=CharField()
            ),
            title=Coalesce(
                "dataset_metadata__title",
                "service_metadata__title",
                "layer__title",
                "feature_type__title",
                "wms__title",
                "wfs__title",
                "csw__title"
            ),
            abstract=Coalesce(
                "dataset_metadata__abstract",
                "service_metadata__abstract",
                "layer__abstract",
                "feature_type__abstract",
                "wms__abstract",
                "wfs__abstract",
                "csw__abstract"
            ),
            bounding_geometry=Coalesce(
                "dataset_metadata__bounding_geometry",
                # TODO: "service_metadata__bounding_geometry",
                "layer__bbox_lat_lon",
                "feature_type__bbox_lat_lon",
                # TODO: get from child layers "wms__bbox_lat_lon",
                # TODO: get from child featuretypes "wfs__bbox_lat_lon",
                # TODO: "csw__bbox_lat_lon"
                output_field=MultiPolygonField()
            ),
            modified_at=Coalesce(
                "dataset_metadata__date_stamp",
                "service_metadata__date_stamp",
                "layer__date_stamp",
                "feature_type__date_stamp",
                "wms__date_stamp",
                "wfs__date_stamp",
                "csw__date_stamp"
            ),
            resource_identifier=Concat(
                F("dataset_metadata__dataset_id_code_space"),
                F("dataset_metadata__dataset_id"),
                output_field=CharField()
            ),
            file_identifier=Coalesce(
                "dataset_metadata__file_identifier",
                "service_metadata__file_identifier",
                Cast("layer__id", CharField()),
                Cast("feature_type__id", CharField()),
                Cast("wms__id", CharField()),
                Cast("wfs__id", CharField()),
                Cast("csw__id", CharField()),
                output_field=CharField()
            ),
            keywords=Case(
                When(
                    hierarchy_level=Value("dataset"),
                    then=ArraySubquery(
                        Keyword.objects.filter(
                            Q(datasetmetadatarecord_metadata__pk=OuterRef(
                                "dataset_metadata__pk"))
                            | Q(layer_metadata__pk=OuterRef("layer__pk"))
                            | Q(featuretype_metadata__pk=OuterRef("feature_type__pk"))
                        ).distinct("keyword").values("keyword")
                    )
                ),
                default=ArraySubquery(
                    Keyword.objects.filter(
                        Q(servicemetadatarecord_metadata__pk=OuterRef(
                            "service_metadata__pk"))
                        | Q(webmapservice_metadata__pk=OuterRef("wms__pk"))
                        | Q(webfeatureservice_metadata__pk=OuterRef("wfs__pk"))
                        | Q(catalogueservice_metadata__pk=OuterRef("csw__pk"))
                    ).distinct("keyword").values("keyword")
                )
            ),
            search=Concat(
                "title",
                Value(" '|' "),
                "abstract",
                Value(" '|' "),
                "keywords",
                output_field=CharField()
            )
        )

        return qs


class IsoMetadataManager(models.Manager):
    """ IsoMetadataManager to handle creation of

    """
    keyword_cls = None
    reference_system_cls = None
    metadata_contact_cls = None
    dataset_contact_cls = None

    def _reset_local_variables(self):
        self.keyword_cls = None
        self.reference_system_cls = None
        self.metadata_contact_cls = None
        self.dataset_contact_cls = None
        # bulk_create will not call the default save() of CommonInfo model. So we need to set the attributes manual. We
        # collect them once.
        if hasattr(HistoricalRecords.context, "request") and hasattr(HistoricalRecords.context.request, "user"):
            self.current_user = HistoricalRecords.context.request.user

    def _create_contact(self, contact):
        from registry.models.metadata import MetadataContact
        contact, _ = MetadataContact.objects.get_or_create(
            **contact.transform_to_model())
        return contact

    def _create_dataset_metadata_record(self, parsed_metadata, origin_url, origin=MetadataOriginEnum.CATALOGUE.value):
        db_metadata_contact = self._create_contact(
            contact=parsed_metadata.metadata_contact)
        db_dataset_contact = self._create_contact(
            contact=parsed_metadata._md_data_identification.dataset_contact)

        field_dict = parsed_metadata.transform_to_model()
        update = False
        defaults = {
            'metadata_contact': db_metadata_contact,
            'dataset_contact': db_dataset_contact,
            'origin': origin,
            'origin_url': origin_url,
            **field_dict,
        }

        try:
            db_dataset_metadata, created = self.model.objects.select_for_update().get_or_create(defaults=defaults, dataset_id=parsed_metadata.dataset_id,
                                                                                                dataset_id_code_space=parsed_metadata.dataset_id_code_space)
        except MultipleObjectsReturned:
            # if dataset_id and dataset_id_code_space is empty, this could happen
            # fallback: search by file_identifier
            db_dataset_metadata, created = self.model.objects.select_for_update().get_or_create(
                defaults=defaults, file_identifier=parsed_metadata.file_identifier)

        if not created:
            with transaction.atomic():
                # TODO: raises AttributeError: 'datetime.date' object has no attribute 'tzinfo' if date_stamp is date
                if isinstance(field_dict["date_stamp"], date):
                    field_dict["date_stamp"] = datetime.combine(
                        field_dict["date_stamp"], datetime.min.time())
                dt_aware = timezone.make_aware(
                    field_dict["date_stamp"], timezone.get_current_timezone())
                if dt_aware > db_dataset_metadata.date_stamp:
                    [setattr(db_dataset_metadata, key, value)
                     for key, value in field_dict]
                    db_dataset_metadata.metadata_contact = db_dataset_contact
                    db_dataset_metadata.dataset_contact = db_dataset_contact
                    db_dataset_metadata.last_modified_by = self.current_user
                    db_dataset_metadata.save()
                    update = True
        return db_dataset_metadata, not created, update

    def _create_service_metadata(self, parsed_metadata, origin_url, origin=MetadataOriginEnum.CATALOGUE.value):
        db_metadata_contact = self._create_contact(
            contact=parsed_metadata.metadata_contact)

        field_dict = parsed_metadata.transform_to_model()
        update = False
        defaults = {
            'metadata_contact': db_metadata_contact,
            'origin': origin,
            'origin_url': origin_url,
            **field_dict,
        }
        file_identifier = defaults.pop("file_identifier")

        db_service_metadata, created = self.model.objects.select_for_update(
        ).get_or_create(defaults=defaults, file_identifier=file_identifier)

        if not created:
            with transaction.atomic():
                # TODO: raises AttributeError: 'datetime.date' object has no attribute 'tzinfo' if date_stamp is date
                if isinstance(field_dict["date_stamp"], date):
                    field_dict["date_stamp"] = datetime.combine(
                        field_dict["date_stamp"], datetime.min.time())
                dt_aware = timezone.make_aware(
                    field_dict["date_stamp"], timezone.get_current_timezone())
                if dt_aware > db_service_metadata.date_stamp:
                    [setattr(db_service_metadata, key, value)
                     for key, value in field_dict]
                    db_service_metadata.metadata_contact = db_metadata_contact
                    db_service_metadata.last_modified_by = self.current_user
                    db_service_metadata.save()
                    update = True
        return db_service_metadata, not created, update

    def update_or_create_from_parsed_metadata(self, parsed_metadata, origin_url, related_object=None, origin=MetadataOriginEnum.CATALOGUE.value):
        self._reset_local_variables()
        with transaction.atomic():
            update = False
            if parsed_metadata.is_service:
                # TODO: update instead of creating, cause we generate service metadata records out of the box from
                #  capabilities
                db_metadata, exists, update = self._create_service_metadata(
                    parsed_metadata=parsed_metadata,
                    origin_url=origin_url,
                    origin=origin)
            elif parsed_metadata.is_dataset:
                db_metadata, exists, update = self._create_dataset_metadata_record(parsed_metadata=parsed_metadata,
                                                                                   origin_url=origin_url,
                                                                                   origin=origin)

                db_metadata.add_dataset_metadata_relation(
                    related_object=related_object)
                if not exists:
                    db_metadata.xml_backup_file.save(name='md_metadata.xml',
                                                     content=ContentFile(str(parsed_metadata.serialize(), "UTF-8")))
                elif update:
                    # TODO: on update we need to check custom metadata
                    # TODO: delete old file
                    db_metadata.xml_backup_file.save(name='md_metadata.xml',
                                                     content=ContentFile(
                                                         str(parsed_metadata.serialize(), "UTF-8")))
            else:
                raise UnknownMetadataKind(
                    "Parsed metadata object is neither describing a service nor describing a dataset. We can't handle it.")
            if not exists and update or not exists and not update:
                db_keyword_list = []
                from registry.models.metadata import \
                    Keyword  # to prevent from circular imports
                for keyword in parsed_metadata.keywords:
                    kwargs = keyword.transform_to_model()
                    if not kwargs:
                        continue
                    try:
                        db_keyword, created = Keyword.objects.get_or_create(
                            **kwargs)
                        db_keyword_list.append(db_keyword)
                    except MultipleObjectsReturned:
                        logger.warning(
                            f"Multiple objects returned for model 'Keyword' with kwargs '{kwargs}'")
                db_metadata.keywords.set(db_keyword_list)

                db_reference_system_list = []
                from registry.models.metadata import \
                    ReferenceSystem  # to prevent from circular imports
                for reference_system in parsed_metadata.reference_systems:
                    kwargs = reference_system.transform_to_model()
                    if not kwargs:
                        continue
                    try:
                        db_reference_system, created = ReferenceSystem.objects.get_or_create(
                            **kwargs)
                        db_reference_system_list.append(db_reference_system)
                    except MultipleObjectsReturned:
                        logger.warning(
                            f"Multiple objects returned for model 'ReferenceSystem' with kwargs '{kwargs}'")
                db_metadata.reference_systems.set(db_reference_system_list)

            # TODO: categories

            return db_metadata, update, exists


class KeywordManager(models.Manager):
    """Needed to insert fixtures without pk by there natural key attribute"""

    def get_by_natural_key(self, keyword):
        return self.get(keyword=keyword)
