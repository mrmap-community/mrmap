import logging

from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.query_utils import Q
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from registry.enums.update import UpdateJobStatusEnum
from registry.managers.update import LayerMappingManager
from registry.mappers.factory import OGCServiceXmlMapper
from registry.mappers.persistence.handler import PersistenceHandler
from registry.models.service import Layer, WebMapService


class LayerMapping(models.Model):
    job = models.ForeignKey(
        to="WebMapServiceUpdateJob",
        on_delete=models.CASCADE,
        related_name="mappings",
        related_query_name="mapping"
    )
    new_layer = models.OneToOneField(
        to=Layer,
        on_delete=models.CASCADE,
        related_name="mapping",
        related_query_name="mapping"
    )
    old_layer = models.OneToOneField(
        to=Layer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reverse_mapping",
        related_query_name="reverse_mapping"
    )
    created = models.DateTimeField(default=now)

    is_confirmed = models.BooleanField(default=False)

    objects = LayerMappingManager()


class WebMapServiceUpdateJob(models.Model):
    SIMILARITY_THRESHOLD = 0.8
    service: WebMapService = models.ForeignKey(
        to=WebMapService,
        on_delete=models.CASCADE,
        null=False,
        verbose_name=_("service"),
        help_text=_("the wms for that this job is running"),
        related_name="update_jobs",
        related_query_name="update_job"
    )
    created = models.DateTimeField(default=now, blank=True, editable=False)
    done_at = models.DateTimeField(null=True, blank=True, editable=False)
    status = models.PositiveSmallIntegerField(
        choices=UpdateJobStatusEnum.choices,
        default=UpdateJobStatusEnum.WAITING_FOR_PROCESSING.value
    )
    keep_customized_metadata = models.BooleanField(
        default=True
    )

    class Meta:
        verbose_name = _("Web Map Service Update Job")
        verbose_name_plural = _("Web Map Service Update Jobs")
        ordering = ["-date_created"]
        get_latest_by = "-date_created"
        indexes = [
            models.Index(fields=["date_created"]),
            models.Index(fields=["done_at"]),
        ]
        constraints = [
            UniqueConstraint(
                fields=["service"],
                condition=Q(done_at__isnull=True),
                name="only_one_unfinished_job_per_service",
                violation_error_message=_(
                    "There is an existing noncompleted job for this service.")
            )
        ]

    def finish(self, status: UpdateJobStatusEnum = UpdateJobStatusEnum.OK):
        self.done_at = now()
        self.status = status.value
        self.save()

    def interrupt(self):
        self.status = UpdateJobStatusEnum.REVIEW_REQUIRED.value
        self.save()

    def check_field(self, name, instance_a, instance_b):
        value_a = getattr(instance_a, name)
        value_b = getattr(instance_b, name)
        result = value_a == value_b
        if not result:
            logging.debug(
                f"field {name} of {type(instance_a)} differs. {value_a} ≠ {value_b}")
        return result

    def update_field(self, name, instance_a, instance_b):
        setattr(instance_a, name, getattr(instance_b, name))

    def get_service_metadata_fields(self):
        return ["title", "abstract"]

    def service_metadata_equal(self, other: WebMapService) -> bool:
        # return True if every check was True, otherwise if any is False it returns False
        return all(
            self.check_field(field_name, self, other)
            for field_name in self.get_service_metadata_fields()
        )

    def get_layer_metadata_fields(self):
        return [
            "title",
            "abstract",
            "is_queryable",
            "is_opaque",
            "is_cascaded",
            "scale_min",
            "scale_max",
            "bbox_lat_lon",
        ]

    def get_layer_structure_fields(self):
        return [
            "mptt_lft",
            "mptt_rgt",
            "mptt_depth"
        ]

    def get_layer_refered_fields(self):
        return [
            "keywords",
            "reference_systems",
            "time_extents"
        ]

    def layer_metadata_equal(self, instance_a, instance_b: Layer) -> bool:
        return all(
            self.check_field(field_name, instance_a, instance_b)
            for field_name in self.get_layer_metadata_fields()
        )

    def create_initial_mappings(self):
        old_layers = list(self.old_service.layers.all())
        new_layers = list(self.new_service.layers.all())

        old_by_identifier = {layer.identifier: layer for layer in old_layers}

        mappings = []

        for new_layer in new_layers:
            old_layer = old_by_identifier.get(new_layer.identifier)

            mappings.append(
                LayerMapping(
                    job=self,
                    new_layer=new_layer,
                    old_layer=old_layer,
                    is_confirmed=old_layer is not None  # optional
                )
            )

        LayerMapping.objects.bulk_create(mappings)

    def create_new_service(self, capabilitites):
        """This will create the service from remote capabilities
           with update_candidate FK set to self.service to identify the service as a temporary dummy
        """
        new_mapping = OGCServiceXmlMapper.from_xml(capabilitites)
        new_mapping.xml_to_django()

        handler = PersistenceHandler(
            mapper=new_mapping,
            defaults={
                "service": {
                    "update_candidate": self.service,
                },
            }
        )
        handler.persist_all()

    @cached_property
    def old_service(self):
        return WebMapService.objects.prefetch_whole_service().get(pk=self.service.pk)

    @cached_property
    def new_service(self):
        return WebMapService.objects.prefetch_whole_service().get(update_candidate=self.service)

    def are_all_layers_updateable(self) -> bool:
        return LayerMapping.objects.is_autoupdate_able(service=self.service)

    def deleteable_layers(self) -> models.QuerySet:
        return Layer.objects.filter(
            service=self.service,
            reverse_mapping__isnull=True
        )

    def updateable_layers(self) -> models.QuerySet:
        return Layer.objects.filter(
            service=self.service,
            mapping__isnull=False,
            reverse_mapping__isnull=False
        )

    def update_layers(self,):
        self.create_initial_mappings()

        if self.are_all_layers_updateable():
            updateable_layers = []
            for mapping in self.mappings.all():
                updateable_layer = mapping.old_layer
                fields = self.get_layer_structure_fields()
                fields += self.get_layer_metadata_fields() if not self.keep_customized_metadata else []

                for field_name in fields:
                    self.update_field(
                        field_name, updateable_layer, mapping.new_layer
                    )
                # TODO: adjust parent link
                updateable_layers.append(updateable_layer)

                for field_name in self.get_layer_refered_fields():
                    # TODO: handle reverse / m2m relations
                    pass

            Layer.objects.bulk_update(
                updateable_layers,
                fields
            )
        else:
            self.interrupt()
            # skip, do nothing. User needs to review this
            return

    def update_service(self):
        """Updates Service metadata if keep customized metadata is not configured.
           Otherwise the user needs to review the processing.
        """
        if not self.service_metadata_equal(self.new_service):
            if not self.keep_customized_metadata:
                # update of service metadata is needed
                for field_name in self.get_service_metadata_fields():
                    self.update_field(
                        field_name, self.service, self.new_service)
                self.service.save()

        # TODO: check service_contact and metadata_contact if there need to be updated

    def update(self):
        remote_capabilities = self.old_service.remote_capabilities

        if self.old_service.document_equals(remote_capabilities):
            # no update needed, cause both capability files are equal
            self.finish()
            return

        self.create_new_service(remote_capabilities)
        self.update_service()
        self.update_layers()
