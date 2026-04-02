from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.query_utils import Q
from django.db.transaction import atomic, on_commit
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from registry.enums.update import UpdateJobStatusEnum
from registry.managers.update import LayerMappingManager
from registry.mappers.factory import OGCServiceXmlMapper
from registry.mappers.persistence.handler import PersistenceHandler
from registry.models.service import Layer, WebMapService
from registry.tasks.update import run_wms_update
from simple_history.utils import bulk_update_with_history


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
    date_created = models.DateTimeField(
        default=now, blank=True, editable=False)
    done_at = models.DateTimeField(null=True, blank=True, editable=False)
    status = models.PositiveSmallIntegerField(
        choices=UpdateJobStatusEnum.choices,
        default=UpdateJobStatusEnum.WAITING_FOR_PROCESSING.value
    )

    # TODO: deprecated -> new plan: create new Model to store WebMapServiceUpdateSettings.
    # With this model the user can define which fields shall be updated or not.
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
                name="only_one_unfinished_update_per_service",
                violation_error_message=_(
                    "There is an existing noncompleted job for this service.")
            )
        ]

    def finish(self, status: UpdateJobStatusEnum = UpdateJobStatusEnum.NO_UPDATE_NEEDED):
        self.done_at = now()
        self.status = status.value
        self.save()

    def interrupt(self):
        self.status = UpdateJobStatusEnum.REVIEW_REQUIRED.value
        self.save()

    def update_field(self, field_name, instance_a, instance_b):
        m2m_fields = [m2m.name for m2m in instance_a._meta.local_many_to_many]
        reverse_fields = [rel.get_accessor_name()
                          for rel in instance_a._meta.related_objects]

        if field_name in m2m_fields:
            instance_a_m2m_field = getattr(instance_a, field_name)
            instance_b_m2m_field = getattr(instance_b, field_name)
            instance_a_m2m_field.set(instance_b_m2m_field.all())
        elif field_name in reverse_fields:
            instance_a_reverse_field = getattr(instance_a, field_name)
            instance_b_reverse_field = getattr(instance_b, field_name)
            instance_a_reverse_field.all().delete()
            instance_a_reverse_field.set(instance_b_reverse_field.all())
        else:  # flat field:
            setattr(instance_a, field_name, getattr(instance_b, field_name))

    @property
    def update_config(self):
        return {
            "WebMapService": {
                "fields": ["title", "abstract", "keywords"]
                # TODO: check service_contact and metadata_contact if there need to be updated

            },
            "Layer": {
                "fields": [
                    "title",
                    "abstract",
                    "is_queryable",
                    "is_opaque",
                    "is_cascaded",
                    "scale_min",
                    "scale_max",
                    "bbox_lat_lon",
                    "mptt_lft",
                    "mptt_rgt",
                    "mptt_depth",
                    "styles",
                    "keywords",
                    "reference_systems",
                    "time_extents"
                ]
            }
        }

    def get_fields_by_model(self, model_cls: models.Model):
        return self.update_config.get(model_cls.__name__, {"fields": []}).get("fields", [])

    def create_initial_layer_mappings(self):
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
           with update_candidate_of FK set to self.service to identify the service as a temporary dummy
        """
        new_mapping = OGCServiceXmlMapper.from_xml(capabilitites)
        new_mapping.xml_to_django()

        handler = PersistenceHandler(
            mapper=new_mapping,
            defaults={
                "WebMapService": {
                    "update_candidate_of": self.service,
                },
            }
        )
        handler.persist_all()

    @cached_property
    def old_service(self):
        return WebMapService.objects.prefetch_whole_service().get(pk=self.service.pk)

    @cached_property
    def new_service(self):
        return WebMapService.objects.prefetch_whole_service().get(update_candidate_of=self.service)

    def are_all_layers_updateable(self) -> bool:
        # if there are new layers without old layer match, then not all layers are updateable
        all_new_layers_updateable = not self.mappings.filter(
            old_layer__isnull=True, is_confirmed=False).exists()

        old_layers_without_match = not Layer.objects.filter(
            service=self.old_service,
            reverse_mapping__isnull=True
        ).exists()

        return all_new_layers_updateable and old_layers_without_match

    def deleteable_layers(self) -> models.QuerySet:
        return Layer.objects.filter(
            service=self.service,
            reverse_mapping__isnull=True
        ).exclude(mapping__isnull=False, mapping__is_confirmed=True)

    def update_layers(self,):
        if self.are_all_layers_updateable():
            old_by_identifier = {
                layer.identifier: layer for layer in self.old_service.layers.all()}

            updateable_layers = []

            fields = self.get_fields_by_model(Layer)

            for mapping in self.mappings.all():
                if mapping.old_layer is None:
                    # This is a new layer without old match. Inject it by changing the service and adjust parent.
                    mapping.new_layer.service = self.service

                    # adjust parent if exists, because the parent might also be a new layer without old match and therefore the parent needs to be set to the new created parent layer (which has the same identifier as the old parent layer)
                    parent = mapping.new_layer.mptt_parent.mapping.old_layer if mapping.new_layer.mptt_parent else None
                    mapping.new_layer.mptt_parent = parent
                    mapping.new_layer.mptt_tree = self.service.root_layer.mptt_tree
                    mapping.new_layer.save()
                    continue

                # regular updating processing of an existing layer with old match. Update the existing layer by adjusting the parent and updating the fields.
                updateable_layer = mapping.old_layer
                new_layer = mapping.new_layer

                updateable_layers.append(updateable_layer)

                # adjust parent
                updateable_layer.mptt_parent = old_by_identifier.get(
                    new_layer.mptt_parent.identifier if new_layer and new_layer.mptt_parent else "")

                for field_name in fields:
                    self.update_field(
                        field_name, updateable_layer, new_layer
                    )

            bulk_update_with_history(
                updateable_layers, Layer, [field.name for field in Layer._meta.concrete_fields if field.name in fields], batch_size=500)

            # clean up everthing we do not longer need
            self.deleteable_layers().delete()

            WebMapService.objects.filter(
                update_candidate_of=self.service).delete()

            self.mappings.all().delete()

            return UpdateJobStatusEnum.UPDATED
        else:
            return UpdateJobStatusEnum.REVIEW_REQUIRED

    def update_service(self):
        """Updates Service metadata if keep customized metadata is not configured.
           Otherwise the user needs to review the processing.
        """
        for field_name in self.get_fields_by_model(WebMapService):
            self.update_field(
                field_name, self.service, self.new_service)
        self.service.save()
        return UpdateJobStatusEnum.UPDATED

    @atomic
    def update(self):
        if self.status not in [
            UpdateJobStatusEnum.REVIEW_REQUIRED.value,
            UpdateJobStatusEnum.UPDATED.value
        ]:

            self.status = UpdateJobStatusEnum.UPDATING.value
            self.save()
            remote_capabilities = self.old_service.remote_capabilities

            if self.old_service.document_equals(remote_capabilities):
                # no update needed, cause both capability files are equal
                self.finish()
                return

            self.create_new_service(remote_capabilities)
            self.create_initial_layer_mappings()

        self.update_service()
        status = self.update_layers()

        self.finish(status)

    def resume(self):
        if self.status != UpdateJobStatusEnum.REVIEW_REQUIRED.value:
            raise ValueError(
                _("Can only resume a job with status REVIEW_REQUIRED"))
        if not self.are_all_layers_updateable():
            raise ValueError(
                _("Cannot resume the job, because not all layers are updateable. Please review the layer mappings first."))
        on_commit(
            lambda: run_wms_update.apply_async(
                update_job_id=(self.pk,)
            )
        )

    def save(self, *args, **kwargs) -> None:
        adding = self._state.adding
        ret = super().save(*args, **kwargs)
        if adding:
            on_commit(
                lambda: run_wms_update.apply_async(
                    update_job_id=(self.pk,)
                )
            )
        return ret


class LayerMapping(models.Model):
    job = models.ForeignKey(
        to=WebMapServiceUpdateJob,
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

    def save(self, *args, **kwargs):
        adding = self._state.adding
        saved = super().save(*args, **kwargs)
        if not adding:
            # try to resume the job if all layers are updateable and the job is currently interrupted
            try:
                self.job.resume()
            except ValueError:
                pass  # just ignore if the job cannot be resumed, because not all layers are updateable or the job is not in the correct status
        return saved
