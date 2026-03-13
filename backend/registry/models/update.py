import logging

from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.query_utils import Q
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from rapidfuzz.distance import Levenshtein
from registry.enums.update import (LayerTreeConflictResolutionEnum,
                                   LayerTreeConflictTypeEnum,
                                   ServiceUpdateConflictEnum,
                                   UpdateJobStatusEnum)
from registry.mappers.factory import OGCServiceXmlMapper
from registry.mappers.persistence.handler import PersistenceHandler
from registry.models.service import Layer, WebMapService


class WebMapServiceUpdateConflict(models.Model):
    service = models.ForeignKey(
        to=WebMapService,
        on_delete=models.CASCADE,
        related_name="conflicts"
    )

    created = models.DateTimeField(auto_now_add=True)
    conflict_type = models.PositiveSmallIntegerField(
        choices=ServiceUpdateConflictEnum.choices
    )
    layer_name = models.CharField(max_length=255)
    description = models.TextField()
    resolved = models.BooleanField(default=False)


class LayerTreeConflict(models.Model):
    existing_layer = models.ForeignKey(
        to=Layer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conflicts",
    )
    remote_identifier = models.CharField(
        max_length=500,
        help_text=_("Identifier found in new capabilities")
    )
    conflict_type = models.PositiveSmallIntegerField(
        choices=LayerTreeConflictTypeEnum.choices,
    )
    details = models.JSONField(
        null=True,
        blank=True,
        help_text=_("Stores structured diff information")
    )
    created = models.DateTimeField(default=now)
    resolved = models.BooleanField(default=False)
    resolution = models.PositiveSmallIntegerField(
        choices=LayerTreeConflictResolutionEnum.choices
    )


class WebMapServiceUpdateJob(models.Model):
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

    def finish(self):
        self.done_at = now()
        self.status = UpdateJobStatusEnum.OK.value
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

    def check_layer_structural(self, instance_a: Layer, instance_b: Layer) -> bool:
        return (
            instance_a.mptt_lft == instance_b.mptt_lft and
            instance_a.mptt_rgt == instance_b.mptt_rgt and
            instance_a.mptt_depth == instance_b.mptt_depth
        )

    def update_service(self):
        db_service = self.service.objects.prefetch_whole_service().get(pk=self.service.pk)

        remote_capabilities = db_service.remote_capabilities

        if db_service.document_equals(remote_capabilities):
            # no update needed, cause both capability files are equal
            self.finish()
            return

        new_mapping = OGCServiceXmlMapper.from_xml(remote_capabilities)
        data = new_mapping.xml_to_django()
        new_service = data[0]

        # run all pre save hooks. Otherwise mptt values are not precalculated
        handler = PersistenceHandler(mapper=new_mapping)
        handler.prepare_for_persist()

        if not self.keep_customized_metadata and not self.service_metadata_equal(new_service):
            # update of service metadata is needed
            for field_name in self.get_service_metadata_fields():
                self.update_field(field_name, db_service, new_service)
            db_service.save()
        # default ordered by mptt_lft value
        db_layers = list(db_service.layers.all())
        parsed_layers = sorted(
            list(new_service._parsed_layers), key=lambda l: l.mptt_lft
        )

        for idx, parsed_layer in enumerate(parsed_layers, 0):
            existing_layer = db_layers[idx]

            if not self.check_layer_structural(existing_layer, parsed_layer):
                LayerTreeConflict(
                    existing_layer=existing_layer,
                    remote_identifier=parsed_layer.identifier,
                    conflict_type=LayerTreeConflictTypeEnum.LAYER_STRUCTURE_CHANGED.value,
                )

            similarity = Levenshtein.normalized_similarity(
                existing_layer.identifier, parsed_layer.identifier)
            if not similarity < 1:
                LayerTreeConflict(
                    existing_layer=existing_layer,
                    remote_identifier=parsed_layer.identifier,
                    conflict_type=LayerTreeConflictTypeEnum.POSSIBLE_LAYER_RENAME.value,
                    details={"similarity": similarity}
                )
