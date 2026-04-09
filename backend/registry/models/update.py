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


def default_update_config():
    return {
        "WebMapService": {
            "title": "overwrite",
            "abstract": "overwrite",
            "keywords": "overwrite",
        },
        "Layer": {
            "title": "overwrite",
            "abstract": "overwrite",
            "identifier": "overwrite",
            "is_queryable": "overwrite",
            "is_opaque": "overwrite",
            "is_cascaded": "overwrite",
            "scale_min": "overwrite",
            "scale_max": "overwrite",
            "bbox_lat_lon": "overwrite",
            "mptt_lft": "overwrite",
            "mptt_rgt": "overwrite",
            "mptt_depth": "overwrite",
            "styles": "overwrite",
            "keywords": "overwrite",
            "reference_systems": "overwrite",
            "time_extents": "overwrite",
        }
    }


class WebMapServiceUpdateConfig(models.Model):
    service = models.OneToOneField(
        to=WebMapService,
        on_delete=models.CASCADE,
        related_name="update_config",
        verbose_name=_("service"),
    )

    config = models.JSONField(default=default_update_config, blank=True)

    class Meta:
        verbose_name = _("Web Map Service Update Config")
        verbose_name_plural = _("Web Map Service Update Configs")


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
        mode = self.get_field_mode(instance_a.__class__, field_name)
        if mode == "ignore":
            return

        m2m_fields = [m2m.name for m2m in instance_a._meta.local_many_to_many]
        reverse_fields = [rel.get_accessor_name()
                          for rel in instance_a._meta.related_objects]

        # -------------------------
        # MANY-TO-MANY
        # -------------------------
        if field_name in m2m_fields:
            instance_a_m2m_field = getattr(instance_a, field_name)
            instance_b_m2m_field = getattr(instance_b, field_name)
            match mode:
                case "overwrite":
                    instance_a_m2m_field.set(instance_b_m2m_field.all())
                case "merge":
                    instance_a_m2m_field.add(*instance_b_m2m_field.all())
                case _:
                    pass
            return

        # -------------------------
        # REVERSE RELATIONS
        # -------------------------
        elif field_name in reverse_fields:
            instance_a_reverse_field = getattr(instance_a, field_name)
            instance_b_reverse_field = getattr(instance_b, field_name)
            match mode:
                case "overwrite":
                    instance_a_reverse_field.all().delete()
                    instance_a_reverse_field.set(
                        instance_b_reverse_field.all())
                case "merge":
                    pass
                case _:
                    pass
            return
        # -------------------------
        # SCALAR FIELDS (default)
        # -------------------------
        if mode == "overwrite":
            setattr(instance_a, field_name, getattr(instance_b, field_name))

    @cached_property
    def update_config(self):
        try:
            return self.service.update_config.config
        except WebMapServiceUpdateConfig.DoesNotExist:
            return default_update_config()

    def get_field_mode(self, model_cls, field_name: str) -> str:
        return (
            self.update_config
            .get(model_cls.__name__, {})
            .get(field_name, "overwrite")
        )

    def get_fields_by_model(self, model_cls):
        return self.update_config.get(model_cls.__name__, {})

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
        """checks if ther are no update conflicts

        “Is there any new layer without mapping?” → must be False

        Returns:
            bool: _description_
        """
        new_layers = self.new_service.layers.all()

        mapped_new_layers = self.mappings.filter(
            is_confirmed=True,
            new_layer__isnull=False
        ).values_list("new_layer", flat=True)

        missing_new = new_layers.exclude(id__in=mapped_new_layers).exists()

        return not missing_new

    def deleteable_layers(self) -> models.QuerySet:
        """All layers of the old service without confirmed mapping"""
        mapped_old_layer_ids = self.mappings.filter(
            old_layer__isnull=False,
            is_confirmed=True
        ).values_list("old_layer_id", flat=True)

        return self.old_service.layers.exclude(pk__in=mapped_old_layer_ids)

    def update_layers(self,):

        if self.are_all_layers_updateable():
            # store deleteable layers, cause after Layer moving to old service,
            # the deleteable layers query would change and we would loose the information which layers we wanted to delete
            deleteable_layers = list(
                self.deleteable_layers().values_list("id", flat=True))

            old_by_identifier = {
                layer.identifier: layer for layer in self.old_service.layers.all()}

            updateable_layers = []

            fields = self.get_fields_by_model(Layer).keys()

            for mapping in self.mappings.exclude(new_layer__isnull=True).all():
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
            Layer.objects.filter(id__in=deleteable_layers).delete()

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
        for field_name in self.get_fields_by_model(WebMapService).keys():
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
                kwargs={"update_job_id": self.pk}
            )
        )

    def save(self, *args, **kwargs) -> None:
        adding = self._state.adding
        ret = super().save(*args, **kwargs)
        if adding:
            on_commit(
                lambda: run_wms_update.apply_async(
                    kwargs={"update_job_id": self.pk}
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
        on_delete=models.CASCADE,
        related_name="reverse_mapping",
        related_query_name="reverse_mapping"
    )
    created = models.DateTimeField(default=now)

    is_confirmed = models.BooleanField(default=False)

    objects = LayerMappingManager()

    class Meta:
        verbose_name = _("Layer Mapping")
        verbose_name_plural = _("Layer Mappings")
        ordering = ["created"]
        indexes = [
            models.Index(fields=["created"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "new_layer"],
                name="unique_new_layer_per_job_in_mapping",
                violation_error_message=_(
                    "A new layer can only be mapped once. Please adjust the layer mappings accordingly.")
            ),
            models.CheckConstraint(
                condition=~(Q(new_layer__isnull=True) &
                            Q(old_layer__isnull=True)),
                name="prevent_both_layers_null",
            ),
        ]

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
