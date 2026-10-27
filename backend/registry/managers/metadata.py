from logging import Logger
from django.conf import settings
from django.db import models, transaction
from registry.enums.metadata import MetadataCouplingKindEnum
from registry.querys.metadata import (MetadataRelationQuerySet,
                                      TimeExtentQuerySet)
from extras.managers import UniqueConstraintDefaultValueManager


logger: Logger = settings.ROOT_LOGGER


class KeywordManager(models.Manager):
    """Needed to insert fixtures without pk by there natural key attribute"""

    def get_by_natural_key(self, keyword):
        return self.get(keyword=keyword)


class DatasetMetadataRecordManager(UniqueConstraintDefaultValueManager):

    def bulk_create(self, *args, **kwargs):
        from registry.models.materialized_views import \
            SearchableDatasetMetadataRecord
        objs = super().bulk_create(*args, **kwargs)
        SearchableDatasetMetadataRecord.refresh()
        return objs

    def bulk_update(self, *args, **kwargs) -> int:
        objs = super().bulk_update(*args, **kwargs)
        from registry.models.materialized_views import \
            SearchableDatasetMetadataRecord
        SearchableDatasetMetadataRecord.refresh()
        return objs


class ServiceMetadataRecordManager(UniqueConstraintDefaultValueManager):

    def bulk_create(self, *args, **kwargs):
        objs = super().bulk_create(*args, **kwargs)
        from registry.models.materialized_views import \
            SearchableServiceMetadataRecord
        SearchableServiceMetadataRecord.refresh()
        return objs

    def bulk_update(self, *args, **kwargs) -> int:
        objs = super().bulk_update(*args, **kwargs)
        from registry.models.materialized_views import \
            SearchableServiceMetadataRecord
        SearchableServiceMetadataRecord.refresh()
        return objs


class TimeExtentManager(models.Manager):

    def get_queryset(self):
        return TimeExtentQuerySet(self.model, using=self._db)

    def with_effective_timerange(self):
        return self.get_queryset().with_effective_timerange()


class MetadataCouplingReferenceManager(models.Manager):
    """ Manager which keeps the derived coupling index of harvested service
        metadata records in sync with their stored xml and answers the inverse
        lookup of a dataset.
    """

    #: The attributes of a CouplingHint with their reference kind, see
    #: :mod:`registry.mappers.parsers.access_links`.
    KIND_OF_ATTRIBUTE = (
        ("uuidref", MetadataCouplingKindEnum.UUIDREF),
        ("href", MetadataCouplingKindEnum.HREF),
        ("identifier", MetadataCouplingKindEnum.IDENTIFIER),
        ("scoped_name", MetadataCouplingKindEnum.SCOPED_NAME),
    )

    def rebuild_for(self, service_metadata):
        """ Regenerate all references which one service metadata record
            advertises.

            Reads the hints out of the record's stored xml through the
            extraction of :mod:`registry.mappers.parsers.access_links`, so an
            already stored record needs no reharvest. A record without a
            readable document simply holds no references, which keeps the
            index free of stale rows when the backup disappears or breaks.

            :param service_metadata: the record whose rows are regenerated
            :type service_metadata: :class:`registry.models.metadata.ServiceMetadataRecord`
            :return: the generated reference rows
            :rtype: list
        """
        from registry.helper.metadata_resolution import stored_xml
        from registry.mappers.parsers.access_links import (ExtractionStatus,
                                                           extract_access_links)
        from registry.models.metadata import MetadataCouplingReference

        keys = set()
        rows = []
        extraction = extract_access_links(
            stored_xml(service_metadata),
            origin_url=service_metadata.origin_url)
        if extraction.status == ExtractionStatus.OK:
            for extracted in extraction.records:
                for hint in extracted.coupling_hints:
                    for attribute, kind in self.KIND_OF_ATTRIBUTE:
                        value = getattr(hint, attribute)
                        if not value:
                            continue
                        key = (kind, value, hint.operation_name or "")
                        if key in keys:
                            continue
                        keys.add(key)
                        rows.append(MetadataCouplingReference(
                            service_metadata=service_metadata,
                            reference_kind=kind.value,
                            value=value[:4096],
                            operation_name=(hint.operation_name or "")[:1024],
                            source=hint.source[:1024],
                        ))
        with transaction.atomic():
            self.filter(service_metadata=service_metadata).delete()
            self.bulk_create(rows)
        return rows

    def for_dataset(self, dataset_record):
        """ Return all references which explicitly name a dataset record.

            The namespaces of the kinds are kept apart: a uuidref names the
            file identifier of a metadata record, while href, identifier and
            scoped name values name the described resource. A resource value
            is therefore matched against the citation code and the combined
            resource identifier, never against the code space alone - which
            would link every dataset of the whole namespace.
        """
        references = self.none()
        if dataset_record.file_identifier:
            references |= self.filter(
                reference_kind=MetadataCouplingKindEnum.UUIDREF.value,
                value=dataset_record.file_identifier)
        identities = {
            value for value in (
                dataset_record.code,
                dataset_record.resource_identifier
                or f"{dataset_record.code_space}{dataset_record.code}")
            if value}
        if identities:
            references |= self.filter(
                reference_kind__in=(
                    MetadataCouplingKindEnum.HREF.value,
                    MetadataCouplingKindEnum.IDENTIFIER.value,
                    MetadataCouplingKindEnum.SCOPED_NAME.value),
                value__in=identities)
        return references.distinct()


class MetadataRelationManager(models.Manager):
    """ Manager which exposes the coupling policy of MrMap, see
        :class:`registry.querys.metadata.MetadataRelationQuerySet`.
    """

    def get_queryset(self):
        return MetadataRelationQuerySet(self.model, using=self._db)

    def imported_evidence(self):
        return self.get_queryset().imported_evidence()

    def local_only(self):
        return self.get_queryset().local_only()

    def publishable(self):
        return self.get_queryset().publishable()
