from datetime import date, datetime

from django.core.exceptions import MultipleObjectsReturned
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.utils import timezone
from registry.enums.metadata import MetadataOrigin
from simple_history.models import HistoricalRecords


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
        contact, created = contact.get_model_class(
        ).objects.get_or_create(**contact.get_field_dict())
        return contact

    def _create_dataset_metadata(self, parsed_metadata, origin_url):
        db_metadata_contact = self._create_contact(
            contact=parsed_metadata.metadata_contact)
        db_dataset_contact = self._create_contact(
            contact=parsed_metadata.md_data_identification.dataset_contact)

        field_dict = parsed_metadata.get_field_dict()
        update = False
        defaults = {
            'metadata_contact': db_metadata_contact,
            'dataset_contact': db_dataset_contact,
            'origin': MetadataOrigin.ISO_METADATA.value,
            'origin_url': origin_url,
            **field_dict,
        }

        try:
            # FIXME use empty string for dataset_id_code_space (avoid multiple identical rows)
            db_dataset_metadata, created = self.model.objects.select_for_update().get_or_create(defaults=defaults, dataset_id=field_dict["dataset_id"],
                                                                                                dataset_id_code_space=field_dict["dataset_id_code_space"])
        except MultipleObjectsReturned:
            # TODO clarify if datasets with NULL dataset_id/dataset_id_code_space can be ruled out somehow?
            db_dataset_metadata = self.model.objects.create(
                dataset_id=field_dict["dataset_id"],
                dataset_id_code_space=field_dict["dataset_id_code_space"],
                **defaults)
            created = True

        if not created:
            with transaction.atomic():
                # todo: raises AttributeError: 'datetime.date' object has no attribute 'tzinfo' if date_stamp is date
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

    def _create_service_metadata(self, parsed_metadata, *args, **kwargs):
        db_metadata_contact = self._create_contact(
            contact=parsed_metadata.metadata_contact).save()

        db_service_metadata = super().create(metadata_contact=db_metadata_contact,
                                             *args,
                                             **kwargs)
        return db_service_metadata

    def update_or_create_from_parsed_metadata(self, parsed_metadata, related_object, origin_url):
        self._reset_local_variables()
        with transaction.atomic():
            update = False
            if parsed_metadata.hierarchy_level == "service":
                # todo: update instead of creating, cause we generate service metadata records out of the box from
                #  capabilities
                db_metadata = self._create_service_metadata(
                    parsed_metadata=parsed_metadata)
            else:
                db_metadata, exists, update = self._create_dataset_metadata(parsed_metadata=parsed_metadata,
                                                                            origin_url=origin_url)

                db_metadata.add_dataset_metadata_relation(
                    related_object=related_object)
                if not exists:
                    db_metadata.xml_backup_file.save(name='md_metadata.xml',
                                                     content=ContentFile(str(parsed_metadata.serializeDocument(), "UTF-8")))
                elif update:
                    # TODO: on update we need to check custom metadata
                    # TODO: delete old file
                    db_metadata.xml_backup_file.save(name='md_metadata.xml',
                                                     content=ContentFile(
                                                         str(parsed_metadata.serializeDocument(), "UTF-8")))
            if update:
                db_keyword_list = []
                for keyword in parsed_metadata.keywords:
                    if not self.keyword_cls:
                        self.keyword_cls = parsed_metadata.keywords[0].get_model_class(
                        )
                    db_keyword, created = self.keyword_cls.objects.get_or_create(
                        **keyword.get_field_dict())
                    db_keyword_list.append(db_keyword)
                db_metadata.keywords.set(*db_keyword_list)

                db_reference_system_list = []
                for reference_system in parsed_metadata.reference_systems:
                    if not self.reference_system_cls:
                        self.reference_system_cls = parsed_metadata.reference_systems[0].get_model_class(
                        )
                    db_reference_system, created = self.reference_system_cls.objects.get_or_create(
                        **reference_system.get_field_dict())
                    db_reference_system_list.append(db_reference_system)
                db_metadata.reference_systems.set(*db_reference_system_list)

            # TODO: categories

            return db_metadata, update, exists


class KeywordManager(models.Manager):
    """Needed to insert fixtures without pk by there natural key attribute"""

    def get_by_natural_key(self, keyword):
        return self.get(keyword=keyword)
