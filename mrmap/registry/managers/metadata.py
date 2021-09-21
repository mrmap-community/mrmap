from django.core.files.base import ContentFile
from django.db import models, transaction, OperationalError
from django.db.models import Count, ExpressionWrapper, BooleanField, F, Q, OuterRef, Subquery, Value, CharField
from django.db.models.functions import Concat
from django.utils.translation import gettext_lazy as _

from registry.enums.metadata import MetadataOrigin
from django.utils import timezone
from datetime import datetime, date


class LicenceManager(models.Manager):
    """
    handles the creation of objects by using the parsed service which is stored in the given :class:`new.Service`
    instance.
    """

    def as_choices(self) -> list:
        """ Returns a list of (identifier, name) to be used as choices in a form

        Returns:
             tuple_list (list): As described above
        """
        return [(licence.identifier, licence.__str__()) for licence in self.get_queryset().filter(is_active=True)]

    def get_descriptions_help_text(self):
        """ Returns a string containing all Licence records for rendering as help_text in a form

        Returns:
             string (str): As described above
        """
        from django.db.utils import ProgrammingError

        try:
            descrs = [
                "<a href='{}' target='_blank'>{}</a>".format(
                    licence.description_url, licence.identifier
                ) for licence in self.get_queryset().all()
            ]
            descr_str = "<br>".join(descrs)
            descr_str = _("Explanations: <br>") + descr_str
        except (ProgrammingError, OperationalError):
            # This will happen on an initial installation. The Licence table won't be created yet, but this function
            # will be called on makemigrations.
            descr_str = ""
        return descr_str


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

    def _create_contact(self, contact):
        contact, created = contact.get_model_class().objects.get_or_create(**contact.get_field_dict())
        return contact

    def _create_dataset_metadata(self, parsed_metadata, origin_url):
        db_metadata_contact = self._create_contact(contact=parsed_metadata.metadata_contact)
        db_dataset_contact = self._create_contact(contact=parsed_metadata.md_data_identification.dataset_contact)

        field_dict = parsed_metadata.get_field_dict()
        update = False
        exists = False
        try:
            db_dataset_metadata = self.model.objects.get(dataset_id=field_dict["dataset_id"],
                                                         dataset_id_code_space=field_dict["dataset_id_code_space"])
            # todo: raises AttributeError: 'datetime.date' object has no attribute 'tzinfo' if date_stamp is date
            if isinstance(field_dict["date_stamp"], date):
                field_dict["date_stamp"] = datetime.combine(field_dict["date_stamp"], datetime.min.time())
            dt_aware = timezone.make_aware(field_dict["date_stamp"], timezone.get_current_timezone())
            if dt_aware > db_dataset_metadata.date_stamp:
                # todo: on update we need to check custom metadata
                self.model.objects.update(metadata_contact=db_metadata_contact,
                                          dataset_contact=db_dataset_contact,
                                          **field_dict)
                update = True
            exists = True
        except self.model.DoesNotExist:
            db_dataset_metadata = super().create(metadata_contact=db_metadata_contact,
                                                 dataset_contact=db_dataset_contact,
                                                 origin=MetadataOrigin.ISO_METADATA.value,
                                                 origin_url=origin_url,
                                                 **field_dict)
        return db_dataset_metadata, exists, update

    def _create_service_metadata(self, parsed_metadata, *args, **kwargs):
        db_metadata_contact = self._create_contact(contact=parsed_metadata.metadata_contact).save()

        db_service_metadata = super().create(metadata_contact=db_metadata_contact,
                                             *args,
                                             **kwargs)
        return db_service_metadata

    def create_from_parsed_metadata(self, parsed_metadata, related_object, origin_url, *args, **kwargs):
        self._reset_local_variables()
        with transaction.atomic():
            update = False
            if parsed_metadata.hierarchy_level == "service":
                # todo: update instead of creating, cause we generate service metadata records out of the box from
                #  capabilities
                db_metadata = self._create_service_metadata(parsed_metadata=parsed_metadata, *args, **kwargs)
            else:
                db_metadata, exists, update = self._create_dataset_metadata(parsed_metadata=parsed_metadata,
                                                                            origin_url=origin_url)

                db_metadata.add_dataset_metadata_relation(related_object=related_object)
                if not exists:
                    db_metadata.xml_backup_file.save(name=f'md_metadata.xml',
                                                     content=ContentFile(str(parsed_metadata.serializeDocument(), "UTF-8")))
                elif update:
                    # todo: on update we need to check custom metadata
                    # todo: delete old file
                    db_metadata.xml_backup_file.save(name=f'md_metadata.xml',
                                                     content=ContentFile(
                                                         str(parsed_metadata.serializeDocument(), "UTF-8")))
            if update:
                db_keyword_list = []
                for keyword in parsed_metadata.keywords:
                    if not self.keyword_cls:
                        self.keyword_cls = parsed_metadata.keywords[0].get_model_class()
                    db_keyword, created = self.keyword_cls.objects.get_or_create(**keyword.get_field_dict())
                    db_keyword_list.append(db_keyword)
                db_metadata.keywords.add(*db_keyword_list)

                db_reference_system_list = []
                for reference_system in parsed_metadata.reference_systems:
                    if not self.reference_system_cls:
                        self.reference_system_cls = parsed_metadata.reference_systems[0].get_model_class()
                    db_reference_system, created = self.reference_system_cls.objects.get_or_create(**reference_system.get_field_dict())
                    db_reference_system_list.append(db_reference_system)
                db_metadata.reference_systems.add(*db_reference_system_list)

            # todo: categories

            return db_metadata


class AbstractMetadataManager(models.Manager):

    def for_table_view(self):
        queryset = self.get_queryset()
        return queryset.select_related("described_object",
                                       "created_by_user",
                                       "owned_by_org") \
                       .order_by("-title")

    def for_detail_view(self):
        return self.get_queryset().select_related("document")\
            .annotate(is_customized=ExpressionWrapper(~Q(document__xml__exact=F("document__xml_backup")),
                                                      output_field=BooleanField()))


class DatasetManager(AbstractMetadataManager):

    def for_table_view(self):
        from quality.models import ConformityCheckRun
        conformity_checks_qs = ConformityCheckRun.objects.order_by("-created_at")
        return self.get_queryset().annotate(linked_layer_count=Count("self_pointing_layers",
                                                                     distinct=True),
                                            linked_feature_type_count=Count("self_pointing_feature_types",
                                                                            distinct=True),
                                            linked_service_count=Count("self_pointing_services",
                                                                       distinct=True),
                                            linked_conformity_check_count=Count("conformitycheckrun",
                                                                                distinct=True),
                                            latest_check_pk=Subquery(conformity_checks_qs.values('pk')[:1]),
                                            latest_check_status=Subquery(conformity_checks_qs.values('passed')[:1]),
                                            latest_check_date=Subquery(conformity_checks_qs.values('created_at')[:1])
                                            )\
            .prefetch_related("self_pointing_layers",
                              "self_pointing_feature_types",
                              "self_pointing_services")\
            .order_by("-title")


class DatasetMetadataRelationManager(models.Manager):

    def get_queryset(self):
        return super().get_queryset().select_related("layer", "feature_type", "dataset_metadata")
