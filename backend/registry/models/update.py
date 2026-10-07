import json
from uuid import uuid4

from django.db import models
from django.db.models import Q
from django.db.models.deletion import Collector
from django.db.transaction import atomic, on_commit
from django.utils.functional import cached_property
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import PeriodicTask
from extras.scheduling import next_run_expected_at
from registry.enums.update import UpdateJobStatusEnum, UpdateModeEnum
from registry.managers.update import LayerMappingManager
from registry.mappers.factory import OGCServiceXmlMapper
from registry.mappers.persistence.handler import PersistenceHandler
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from registry.tasks.update import (run_csw_update, run_wfs_update,
                                   run_wms_update)
from simple_history.utils import bulk_update_with_history


def default_wms_update_config() -> dict[str, dict[str, UpdateModeEnum]]:
    return {
        "WebMapService": {
            "title": UpdateModeEnum.OVERWRITE,
            "abstract": UpdateModeEnum.OVERWRITE,
            "keywords": UpdateModeEnum.OVERWRITE,
        },
        "Layer": {
            "title": UpdateModeEnum.OVERWRITE,
            "abstract": UpdateModeEnum.OVERWRITE,
            "identifier": UpdateModeEnum.OVERWRITE,
            "is_queryable": UpdateModeEnum.OVERWRITE,
            "is_opaque": UpdateModeEnum.OVERWRITE,
            "is_cascaded": UpdateModeEnum.OVERWRITE,
            "scale_min": UpdateModeEnum.OVERWRITE,
            "scale_max": UpdateModeEnum.OVERWRITE,
            "bbox_lat_lon": UpdateModeEnum.OVERWRITE,
            "mptt_lft": UpdateModeEnum.OVERWRITE,
            "mptt_rgt": UpdateModeEnum.OVERWRITE,
            "mptt_depth": UpdateModeEnum.OVERWRITE,
            "styles": UpdateModeEnum.OVERWRITE,
            "keywords": UpdateModeEnum.OVERWRITE,
            "reference_systems": UpdateModeEnum.OVERWRITE,
            "time_extents": UpdateModeEnum.OVERWRITE,
            # TODO: datasetmetadata overwrite
        },
    }


def default_wfs_update_config() -> dict[str, dict[str, UpdateModeEnum]]:
    return {
        "WebFeatureService": {
            "title": UpdateModeEnum.OVERWRITE,
            "abstract": UpdateModeEnum.OVERWRITE,
            "keywords": UpdateModeEnum.OVERWRITE,
        },
        "FeatureType": {
            "title": UpdateModeEnum.OVERWRITE,
            "abstract": UpdateModeEnum.OVERWRITE,
            "identifier": UpdateModeEnum.OVERWRITE,
            "bbox_lat_lon": UpdateModeEnum.OVERWRITE,
            "keywords": UpdateModeEnum.OVERWRITE,
            "default_reference_system": UpdateModeEnum.OVERWRITE,
            "reference_systems": UpdateModeEnum.OVERWRITE,
        },
    }


def default_csw_update_config() -> dict[str, dict[str, UpdateModeEnum]]:
    return {
        "CatalogueService": {
            "title": UpdateModeEnum.OVERWRITE,
            "abstract": UpdateModeEnum.OVERWRITE,
            "keywords": UpdateModeEnum.OVERWRITE,
            "max_step_size": UpdateModeEnum.OVERWRITE,
            "output_formats": UpdateModeEnum.OVERWRITE,
        },
    }


class WebMapServiceUpdateSetting(PeriodicTask):
    @property
    def next_run_expected_at(self):
        return next_run_expected_at(self)

    service: WebMapService = models.ForeignKey(
        to=WebMapService,
        on_delete=models.CASCADE,
        related_name="web_map_service_update_settings",
        related_query_name="web_map_service_update_setting",
        verbose_name=_("web map service"),
        help_text=_("this is the service which shall be updated"))

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self.pk:
            if not self.task:
                self.task = "registry.tasks.update.create_wms_update_job"
            if not self.queue:
                self.queue = "update"
            if not self.name:
                self.name = str(uuid4())
            if not self.kwargs or self.kwargs == '{}':
                self.kwargs = json.dumps({
                    "name": str(self.name),
                })


class WebMapServiceUpdateConfig(models.Model):
    service = models.OneToOneField(
        to=WebMapService,
        on_delete=models.CASCADE,
        related_name="update_config",
        verbose_name=_("service"),
    )

    config = models.JSONField(default=default_wms_update_config, blank=True)

    class Meta:
        verbose_name = _("Web Map Service Update Config")
        verbose_name_plural = _("Web Map Service Update Configs")


class WebFeatureServiceUpdateSetting(PeriodicTask):
    @property
    def next_run_expected_at(self):
        return next_run_expected_at(self)

    service: WebFeatureService = models.ForeignKey(
        to=WebFeatureService,
        on_delete=models.CASCADE,
        related_name="web_feature_service_update_settings",
        related_query_name="web_feature_service_update_setting",
        verbose_name=_("web feature service"),
        help_text=_("this is the service which shall be updated"))

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self.pk:
            if not self.task:
                self.task = "registry.tasks.update.create_wfs_update_job"
            if not self.queue:
                self.queue = "update"
            if not self.name:
                self.name = str(uuid4())
            if not self.kwargs or self.kwargs == '{}':
                self.kwargs = json.dumps({
                    "name": str(self.name),
                })


class WebFeatureServiceUpdateConfig(models.Model):
    service = models.OneToOneField(
        to=WebFeatureService,
        on_delete=models.CASCADE,
        related_name="update_config",
        verbose_name=_("service"),
    )

    config = models.JSONField(default=default_wfs_update_config, blank=True)

    class Meta:
        verbose_name = _("Web Feature Service Update Config")
        verbose_name_plural = _("Web Feature Service Update Configs")


class CatalogueServiceUpdateSetting(PeriodicTask):
    @property
    def next_run_expected_at(self):
        return next_run_expected_at(self)

    service: CatalogueService = models.ForeignKey(
        to=CatalogueService,
        on_delete=models.CASCADE,
        related_name="catalogue_service_update_settings",
        related_query_name="catalogue_service_update_setting",
        verbose_name=_("catalogue service"),
        help_text=_("this is the service which shall be updated"))

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if not self.pk:
            if not self.task:
                self.task = "registry.tasks.update.create_csw_update_job"
            if not self.queue:
                self.queue = "update"
            if not self.name:
                self.name = str(uuid4())
            if not self.kwargs or self.kwargs == '{}':
                self.kwargs = json.dumps({
                    "name": str(self.name),
                })


class CatalogueServiceUpdateConfig(models.Model):
    service = models.OneToOneField(
        to=CatalogueService,
        on_delete=models.CASCADE,
        related_name="update_config",
        verbose_name=_("service"),
    )

    config = models.JSONField(default=default_csw_update_config, blank=True)

    class Meta:
        verbose_name = _("Web Catalogue Service Update Config")
        verbose_name_plural = _("Web Catalogue Service Update Configs")


class ServiceUpdateJob(models.Model):
    date_created = models.DateTimeField(auto_now_add=True, editable=False)
    done_at = models.DateTimeField(null=True, editable=False)
    status = models.PositiveSmallIntegerField(
        choices=UpdateJobStatusEnum.choices,
        default=UpdateJobStatusEnum.WAITING_FOR_PROCESSING.value,
    )

    class Meta:
        abstract = True
        ordering = ["-date_created"]
        get_latest_by = "-date_created"
        indexes = [
            models.Index(fields=["date_created"]),
            models.Index(fields=["done_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["service"],
                condition=Q(done_at__isnull=True),
                name="%(app_label)s_%(class)s_only_one_unfinished_update_per_service",
                violation_error_message=_(
                    "There is an existing noncompleted job for this service."),
            )
        ]

    @atomic
    def update(self):
        raise NotImplementedError

    def resume(self):
        raise NotImplementedError

    def finish(self, status: UpdateJobStatusEnum = UpdateJobStatusEnum.NO_UPDATE_NEEDED):
        self.done_at = now()
        self.status = status.value
        self.save()

    def interrupt(self):
        self.status = UpdateJobStatusEnum.REVIEW_REQUIRED.value
        self.save()

    @property
    def default_change_reason(self):
        return f"updatejob_id: {self.pk}"

    def update_field(self, field_name, instance_a, instance_b) -> bool:
        """Apply the configured mode and report whether the value changed."""
        mode = self.get_field_mode(type(instance_a), field_name)
        if mode == UpdateModeEnum.IGNORE:
            return False

        m2m_fields = {field.name for field in instance_a._meta.many_to_many}
        reverse_fields = {
            rel.get_accessor_name() for rel in instance_a._meta.related_objects
        }
        if field_name in m2m_fields or field_name in reverse_fields:
            target = getattr(instance_a, field_name)
            source = getattr(instance_b, field_name)
            old_ids = set(target.all().values_list("pk", flat=True))
            new_objects = list(source.all())
            new_ids = {obj.pk for obj in new_objects}
            if mode == UpdateModeEnum.OVERWRITE:
                if old_ids == new_ids:
                    return False
                if field_name in reverse_fields:
                    # Preserve the original ownership-transfer semantics. Materialize
                    # the source first, before deleting the old owned objects.
                    target.exclude(pk__in=new_ids).delete()
                target.set(new_objects)
                return True
            if mode == UpdateModeEnum.MERGE and field_name in m2m_fields:
                additions = [
                    obj for obj in new_objects if obj.pk not in old_ids]
                if additions:
                    target.add(*additions)
                    return True
            return False

        if mode != UpdateModeEnum.OVERWRITE:
            return False
        field = instance_a._meta.get_field(field_name)
        attribute = field.attname
        old_value = getattr(instance_a, attribute)
        new_value = getattr(instance_b, attribute)
        if old_value == new_value:
            return False
        setattr(instance_a, attribute, new_value)
        return True

    def update_metadata(self, model):
        changed = False
        self.service._change_reason = self.default_change_reason
        for field_name in self.get_fields_by_model(model):
            changed |= self.update_field(
                field_name, self.service, self.new_service)
        if changed:
            self.service.save()
        return UpdateJobStatusEnum.UPDATED

    def bulk_update_changed(self, objects, model, configured_fields, extra_fields=()):
        if not objects:
            return
        field_names = set(configured_fields) | set(extra_fields)
        fields = [field.name for field in model._meta.concrete_fields
                  if field.name in field_names and not field.primary_key]
        if not fields:
            model.history.bulk_history_create(
                objects, update=True,
                default_change_reason=self.default_change_reason, batch_size=500,
            )
            return
        bulk_update_with_history(
            objects, model, fields,
            default_change_reason=self.default_change_reason,
            batch_size=500,
        )

    def adopt_candidate(self, instance):
        """Persist a promoted candidate, then record its addition to the real service."""
        instance._change_reason = self.default_change_reason
        had_skip = hasattr(instance, "skip_history_when_saving")
        previous_skip = getattr(instance, "skip_history_when_saving", None)
        instance.skip_history_when_saving = True
        try:
            instance.save()
        finally:
            if had_skip:
                instance.skip_history_when_saving = previous_skip
            else:
                del instance.skip_history_when_saving
        # bulk_history_create defaults to '+'; it does not insert the live object.
        instance.history.bulk_history_create(
            [instance], default_change_reason=self.default_change_reason,
        )

    def delete_with_reason(self, queryset, model):
        collector = Collector(using=queryset.db, origin=queryset)
        collector.collect(queryset)
        for instance in collector.data.get(model, ()):
            instance._change_reason = self.default_change_reason
        collector.delete()

    @cached_property
    def update_config(self) -> dict[str, dict[str, UpdateModeEnum]]:
        raise NotImplementedError

    def get_field_mode(self, model_cls, field_name: str) -> UpdateModeEnum:
        return self.update_config.get(model_cls.__name__, {}).get(field_name, UpdateModeEnum.OVERWRITE)

    def get_fields_by_model(self, model_cls):
        return self.update_config.get(model_cls.__name__, {})


class WebMapServiceUpdateJob(ServiceUpdateJob):
    service = models.ForeignKey(
        to=WebMapService,
        on_delete=models.CASCADE,
        null=False,
        verbose_name=_("service"),
        help_text=_("the wms this job is running for"),
        related_name="update_jobs",
        related_query_name="update_job",
    )

    class Meta(ServiceUpdateJob.Meta):
        verbose_name = _("Web Map Service Update Job")
        verbose_name_plural = _("Web Map Service Update Jobs")

    @property
    def default_change_reason(self):
        return f"updatejob_id: {self.pk}"

    @cached_property
    def update_config(self) -> dict[str, dict[str, UpdateModeEnum]]:
        try:
            return self.service.update_config.config
        except WebMapServiceUpdateConfig.DoesNotExist:
            return default_wms_update_config()

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
                    is_confirmed=old_layer is not None,  # optional
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
            },
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

        mapped_new_layers = self.mappings.filter(is_confirmed=True, new_layer__isnull=False).values_list(
            "new_layer", flat=True
        )

        missing_new = new_layers.exclude(id__in=mapped_new_layers).exists()

        return not missing_new

    def deleteable_layers(self) -> models.QuerySet:
        """All layers of the old service without confirmed mapping"""
        mapped_old_layer_ids = self.mappings.filter(old_layer__isnull=False, is_confirmed=True).values_list(
            "old_layer_id", flat=True
        )

        return self.old_service.layers.exclude(pk__in=mapped_old_layer_ids)

    @atomic
    def update_layers(self):
        if not self.are_all_layers_updateable():
            return UpdateJobStatusEnum.REVIEW_REQUIRED

        deleteable_layers = list(
            self.deleteable_layers().values_list("id", flat=True))
        mappings = list(self.mappings.filter(
            is_confirmed=True, new_layer__isnull=False,
        ).select_related("new_layer", "old_layer"))
        # Resolve by candidate ID, so renamed and newly adopted parents both work.
        targets = {
            mapping.new_layer_id: (
                mapping.old_layer if mapping.old_layer_id else mapping.new_layer
            ) for mapping in mappings
        }
        fields = self.get_fields_by_model(Layer)
        updateable_layers = []
        adopted_layers = []
        tree = self.service.root_layer.mptt_tree
        for mapping in mappings:
            new_layer = mapping.new_layer
            target = targets[mapping.new_layer_id]
            parent = targets[new_layer.mptt_parent_id] if new_layer.mptt_parent_id else None
            if mapping.old_layer_id is None:
                target.service = self.service
                target.mptt_parent = parent
                target.mptt_tree = tree
                adopted_layers.append(target)
                continue

            target._change_reason = self.default_change_reason
            changed = target.mptt_parent_id != (parent.pk if parent else None)
            target.mptt_parent = parent
            for field_name in fields:
                changed |= self.update_field(field_name, target, new_layer)
            if changed:
                updateable_layers.append(target)

        self.bulk_update_changed(
            updateable_layers, Layer, fields, ("mptt_parent",))
        # Update directly to retain the candidate's supplied tree coordinates;
        # Node.save() may otherwise recalculate them during adoption.
        if adopted_layers:
            for layer in adopted_layers:
                layer._change_reason = self.default_change_reason
            Layer.objects.bulk_update(
                adopted_layers, ["service", "mptt_parent", "mptt_tree"], batch_size=500,
            )
            Layer.history.bulk_history_create(
                adopted_layers, default_change_reason=self.default_change_reason,
                batch_size=500,
            )
        self.delete_with_reason(Layer.objects.filter(
            id__in=deleteable_layers), Layer)
        WebMapService.objects.filter(update_candidate_of=self.service).delete()
        self.mappings.all().delete()
        return UpdateJobStatusEnum.UPDATED

    def update_service(self):
        return self.update_metadata(WebMapService)

    @atomic
    def update(self):
        if self.status not in [
            UpdateJobStatusEnum.REVIEW_REQUIRED.value,
            UpdateJobStatusEnum.UPDATED.value,
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

        if status == UpdateJobStatusEnum.REVIEW_REQUIRED:
            self.done_at = None
            self.interrupt()
        else:
            self.finish(status)

    def resume(self):
        if self.status != UpdateJobStatusEnum.REVIEW_REQUIRED.value:
            raise ValueError(
                _("Can only resume a job with status REVIEW_REQUIRED"))
        if not self.are_all_layers_updateable():
            raise ValueError(
                _(
                    "Cannot resume the job, because not all layers are updateable. Please review the layer mappings first."
                )
            )
        on_commit(lambda: run_wms_update.apply_async(
            kwargs={"update_job_id": self.pk}))

    def save(self, *args, **kwargs):
        adding = self._state.adding
        super().save(*args, **kwargs)
        if adding:
            on_commit(lambda: run_wms_update.apply_async(
                kwargs={"update_job_id": self.pk}))


class WebFeatureServiceUpdateJob(ServiceUpdateJob):
    service = models.ForeignKey(
        to=WebFeatureService,
        on_delete=models.CASCADE,
        verbose_name=_("service"),
        help_text=_("the WFS this job is running for"),
        related_name="update_jobs",
        related_query_name="update_job",
    )

    class Meta(ServiceUpdateJob.Meta):
        verbose_name = _("Web Feature Service Update Job")
        verbose_name_plural = _("Web Feature Service Update Jobs")

    @cached_property
    def update_config(self) -> dict[str, dict[str, UpdateModeEnum]]:
        try:
            return self.service.update_config.config
        except WebFeatureServiceUpdateConfig.DoesNotExist:
            return default_wfs_update_config()

    def create_initial_featuretype_mappings(self):
        old_featuretypes = list(self.old_service.featuretypes.all())
        new_featuretypes = list(self.new_service.featuretypes.all())

        old_by_identifier = {
            featuretype.identifier: featuretype for featuretype in old_featuretypes}

        mappings = []

        for new_featuretype in new_featuretypes:
            old_featuretype = old_by_identifier.get(new_featuretype.identifier)

            mappings.append(
                FeatureTypeMapping(
                    job=self,
                    new_featuretype=new_featuretype,
                    old_featuretype=old_featuretype,
                    is_confirmed=old_featuretype is not None,  # optional
                )
            )

        FeatureTypeMapping.objects.bulk_create(mappings)

    def create_new_service(self, capabilitites):
        """This will create the service from remote capabilities
        with update_candidate_of FK set to self.service to identify the service as a temporary dummy
        """
        new_mapping = OGCServiceXmlMapper.from_xml(capabilitites)
        new_mapping.xml_to_django()

        handler = PersistenceHandler(
            mapper=new_mapping,
            defaults={
                "WebFeatureService": {
                    "update_candidate_of": self.service,
                },
            },
        )
        handler.persist_all()

    @cached_property
    def old_service(self):
        return WebFeatureService.objects.prefetch_whole_service().get(pk=self.service.pk)

    @cached_property
    def new_service(self):
        return WebFeatureService.objects.prefetch_whole_service().get(update_candidate_of=self.service)

    def are_all_featuretypes_updateable(self) -> bool:
        """checks if ther are no update conflicts

        “Is there any new featuretype without mapping?” → must be False

        Returns:
            bool: _description_
        """
        new_featuretypes = self.new_service.featuretypes.all()

        mapped_new_featuretypes = self.mappings.filter(is_confirmed=True, new_featuretype__isnull=False).values_list(
            "new_featuretype", flat=True
        )

        missing_new = new_featuretypes.exclude(
            id__in=mapped_new_featuretypes).exists()

        return not missing_new

    def deleteable_featuretypes(self) -> models.QuerySet:
        """All featuretypes of the old service without confirmed mapping"""
        mapped_old_featuretypes_ids = self.mappings.filter(old_featuretype__isnull=False, is_confirmed=True).values_list(
            "old_featuretype_id", flat=True
        )

        return self.old_service.featuretypes.exclude(pk__in=mapped_old_featuretypes_ids)

    @atomic
    def update_featuretypes(self) -> UpdateJobStatusEnum:
        if not self.are_all_featuretypes_updateable():
            return UpdateJobStatusEnum.REVIEW_REQUIRED
        deleteable_featuretypes = list(
            self.deleteable_featuretypes().values_list("id", flat=True)
        )
        fields = self.get_fields_by_model(FeatureType)
        updateable_featuretypes = []
        for mapping in self.mappings.filter(
            is_confirmed=True, new_featuretype__isnull=False,
        ).select_related("new_featuretype", "old_featuretype"):
            if mapping.old_featuretype_id is None:
                mapping.new_featuretype.service = self.service
                self.adopt_candidate(mapping.new_featuretype)
                continue
            target = mapping.old_featuretype
            target._change_reason = self.default_change_reason
            changed = False
            for field_name in fields:
                changed |= self.update_field(
                    field_name, target, mapping.new_featuretype)
            if changed:
                updateable_featuretypes.append(target)
        self.bulk_update_changed(updateable_featuretypes, FeatureType, fields)
        self.delete_with_reason(
            FeatureType.objects.filter(
                id__in=deleteable_featuretypes), FeatureType,
        )
        WebFeatureService.objects.filter(
            update_candidate_of=self.service).delete()
        self.mappings.all().delete()
        return UpdateJobStatusEnum.UPDATED

    def update_service(self):
        return self.update_metadata(WebFeatureService)

    @atomic
    def update(self):
        if self.status not in [
            UpdateJobStatusEnum.REVIEW_REQUIRED.value,
            UpdateJobStatusEnum.UPDATED.value,
        ]:
            self.status = UpdateJobStatusEnum.UPDATING.value
            self.save()
            remote_capabilities = self.old_service.remote_capabilities

            if self.old_service.document_equals(remote_capabilities):
                # no update needed, cause both capability files are equal
                self.finish()
                return

            self.create_new_service(remote_capabilities)
            self.create_initial_featuretype_mappings()

        self.update_service()
        status = self.update_featuretypes()

        if status == UpdateJobStatusEnum.REVIEW_REQUIRED:
            self.done_at = None
            self.interrupt()
        else:
            self.finish(status)

    def resume(self):
        if self.status != UpdateJobStatusEnum.REVIEW_REQUIRED.value:
            raise ValueError(
                _("Can only resume a job with status REVIEW_REQUIRED"))
        if not self.are_all_featuretypes_updateable():
            raise ValueError(
                _(
                    "Cannot resume the job, because not all featuretypes are updateable. Please review the featuretype mappings first."
                )
            )
        on_commit(lambda: run_wfs_update.apply_async(
            kwargs={"update_job_id": self.pk}))

    def save(self, *args, **kwargs):
        adding = self._state.adding
        super().save(*args, **kwargs)
        if adding:
            on_commit(lambda: run_wfs_update.apply_async(
                kwargs={"update_job_id": self.pk}))


class CatalogueServiceUpdateJob(ServiceUpdateJob):
    service = models.ForeignKey(
        to=CatalogueService,
        on_delete=models.CASCADE,
        verbose_name=_("service"),
        help_text=_("the CSW this job is running for"),
        related_name="update_jobs",
        related_query_name="update_job",
    )

    class Meta(ServiceUpdateJob.Meta):
        verbose_name = _("Web Catalogue Service Update Job")
        verbose_name_plural = _("Web Catalogue Service Update Jobs")

    @cached_property
    def update_config(self) -> dict[str, dict[str, UpdateModeEnum]]:
        try:
            return self.service.update_config.config
        except CatalogueServiceUpdateConfig.DoesNotExist:
            return default_csw_update_config()

    def create_new_service(self, capabilitites):
        """This will create the service from remote capabilities
        with update_candidate_of FK set to self.service to identify the service as a temporary dummy
        """
        new_mapping = OGCServiceXmlMapper.from_xml(capabilitites)
        new_mapping.xml_to_django()

        handler = PersistenceHandler(
            mapper=new_mapping,
            defaults={
                "CatalogueService": {
                    "update_candidate_of": self.service,
                },
            },
        )
        handler.persist_all()

    @cached_property
    def old_service(self):
        return CatalogueService.objects.prefetch_whole_service().get(pk=self.service.pk)

    @cached_property
    def new_service(self):
        return CatalogueService.objects.prefetch_whole_service().get(update_candidate_of=self.service)

    def update_service(self):
        return self.update_metadata(CatalogueService)

    @atomic
    def update(self):
        if self.status not in [
            UpdateJobStatusEnum.REVIEW_REQUIRED.value,
            UpdateJobStatusEnum.UPDATED.value,
        ]:
            self.status = UpdateJobStatusEnum.UPDATING.value
            self.save()
            remote_capabilities = self.old_service.remote_capabilities

            if self.old_service.document_equals(remote_capabilities):
                # no update needed, cause both capability files are equal
                self.finish()
                return

            self.create_new_service(remote_capabilities)

        self.update_service()

        self.finish(UpdateJobStatusEnum.UPDATED)

    def resume(self):
        if self.status != UpdateJobStatusEnum.REVIEW_REQUIRED.value:
            raise ValueError(
                _("Can only resume a job with status REVIEW_REQUIRED"))
        on_commit(lambda: run_csw_update.apply_async(
            kwargs={"update_job_id": self.pk}))

    def save(self, *args, **kwargs):
        adding = self._state.adding
        super().save(*args, **kwargs)
        if adding:
            on_commit(lambda: run_csw_update.apply_async(
                kwargs={"update_job_id": self.pk}))


class ServiceElementMapping(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    is_confirmed = models.BooleanField(default=False)

    class Meta:
        abstract = True
        ordering = ["created"]
        indexes = [
            models.Index(fields=["created"]),
        ]

    def save(self, *args, **kwargs):
        adding = self._state.adding
        super().save(*args, **kwargs)
        if not adding:
            if isinstance(self, LayerMapping):
                # Check readiness in the worker after all review changes commit.
                job_id = self.job_id
                on_commit(lambda: run_wms_update.apply_async(
                    kwargs={"update_job_id": job_id}))
                return
            # try to resume the job if all elements are updateable and the job is currently interrupted
            try:
                self.job.resume()
            except ValueError:
                pass  # just ignore if the job cannot be resumed, because not all elements are updateable or the job is not in the correct status


class LayerMapping(ServiceElementMapping):
    job = models.ForeignKey(
        to=WebMapServiceUpdateJob,
        on_delete=models.CASCADE,
        related_name="mappings",
        related_query_name="mapping",
    )
    new_layer = models.OneToOneField(
        to=Layer,
        on_delete=models.CASCADE,
        related_name="mapping",
        related_query_name="mapping",
    )
    old_layer = models.OneToOneField(
        to=Layer,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reverse_mapping",
        related_query_name="reverse_mapping",
    )

    objects = LayerMappingManager()

    class Meta(ServiceElementMapping.Meta):
        verbose_name = _("Layer Mapping")
        verbose_name_plural = _("Layer Mappings")
        constraints = [
            models.UniqueConstraint(
                fields=["job", "new_layer"],
                name="unique_new_layer_per_job_in_mapping",
                violation_error_message=_(
                    "A new layer can only be mapped once. Please adjust the layer mappings accordingly."
                ),
            ),
            models.CheckConstraint(
                condition=~(Q(new_layer__isnull=True) &
                            Q(old_layer__isnull=True)),
                name="prevent_both_layers_null",
            ),
        ]


class FeatureTypeMapping(ServiceElementMapping):
    job = models.ForeignKey(
        to=WebFeatureServiceUpdateJob,
        on_delete=models.CASCADE,
        related_name="mappings",
        related_query_name="mapping",
    )
    new_featuretype = models.OneToOneField(
        to="registry.FeatureType",
        on_delete=models.CASCADE,
        related_name="mapping",
        related_query_name="mapping",
    )
    old_featuretype = models.OneToOneField(
        to="registry.FeatureType",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="reverse_mapping",
        related_query_name="reverse_mapping",
    )

    class Meta(ServiceElementMapping.Meta):
        verbose_name = _("Feature Type Mapping")
        verbose_name_plural = _("Feature Type Mappings")
        constraints = [
            models.UniqueConstraint(
                fields=["job", "new_featuretype"],
                name="unique_new_featuretype_per_job_in_mapping",
                violation_error_message=_(
                    "A new feature type can only be mapped once. Please adjust the feature type mappings accordingly."
                ),
            ),
            models.CheckConstraint(
                condition=~(Q(new_featuretype__isnull=True) &
                            Q(old_featuretype__isnull=True)),
                name="prevent_both_featuretypes_null",
            ),
        ]
