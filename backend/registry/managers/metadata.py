from datetime import date, datetime
from logging import Logger

from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.utils import timezone
from extras.managers import UniqueConstraintDefaultValueManager
from registry.enums.metadata import MetadataOriginEnum
from registry.exceptions.metadata import UnknownMetadataKind
from simple_history.models import HistoricalRecords

logger: Logger = settings.ROOT_LOGGER


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
        if contact:
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
            db_dataset_metadata, created = self.model.objects.select_for_update().get_or_create(defaults=defaults, code=parsed_metadata.code,
                                                                                                code_space=parsed_metadata.code_space)
        except MultipleObjectsReturned:
            # if code and code_space is empty, this could happen
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
                     for key, value in field_dict.items()]
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

        try:
            db_service_metadata, created = self.model.objects.select_for_update(
            ).get_or_create(defaults=defaults, code=parsed_metadata.code, code_space=parsed_metadata.code_space)
        except MultipleObjectsReturned:
            # if code and code_space is empty, this could happen
            # fallback: search by file_identifier
            db_service_metadata, created = self.model.objects.select_for_update().get_or_create(
                defaults=defaults, file_identifier=parsed_metadata.file_identifier)

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
                     for key, value in field_dict.items()]
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
                for keyword in list(filter(
                        lambda k: k != "" and k != None, [keyword.keyword for keyword in parsed_metadata.keywords])):
                    kwargs = {"keyword": keyword}
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
                        db_reference_system_list.append(
                            db_reference_system)
                    except MultipleObjectsReturned:
                        logger.warning(
                            f"Multiple objects returned for model 'ReferenceSystem' with kwargs '{kwargs}'")
                db_metadata.reference_systems.set(db_reference_system_list)

            return db_metadata, update, exists


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
