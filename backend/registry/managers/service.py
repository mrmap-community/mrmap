from django.db.models import (Exists, F, Manager, OuterRef, Prefetch, QuerySet,
                              Value, Window)
from django.db.models.functions import Coalesce, RowNumber
from extras.managers import DefaultHistoryManager
from mptt2.managers import TreeManager
from registry import models
from registry.querys.service import LayerQuerySet

SIBLING_INDEX = Coalesce(
    Window(
        expression=RowNumber(),
        partition_by=[F("mptt_parent")],
        order_by=F("mptt_lft").asc(),
    ) - 1,
    Value(0),
)


def configured_relation_fields(model, config_section) -> list:
    """Names of the relation fields a service update config names for a model.

    Mirrors the field dispatch of ``ServiceUpdateJob.update_field``: scalar
    fields — plain columns as well as concrete FK ids — are compared out of
    the row itself and need no read plan; only M2M and reverse fields are
    read through the relation and must be carried by a plan (#1393).
    """
    m2m_fields = {field.name for field in model._meta.many_to_many}
    reverse_fields = {
        rel.get_accessor_name() for rel in model._meta.related_objects}
    return [
        name for name in (config_section or {})
        if name in m2m_fields or name in reverse_fields]


class ServiceAlertQuerySetMixin:
    """The states of the services of one kind which need attention.

    The rules which decide about these states are not answered here but in
    registry/querys/alerts.py, which is imported on the way, because the models
    the rules are derived from use the managers of the services themselves.
    """

    def with_alert_information(self):
        """Annotate the states of these services which need attention.

        Returns:
            the queryset with the alerts of every service annotated
        """
        from registry.querys.alerts import alert_annotations
        return alert_annotations(self)


class VisibilityQuerySetMixin:
    """The tri-state answer of #739, as an annotation.

    ``visibility`` reads the guardian grants of every row in the list's own
    SELECT - two ``EXISTS`` subqueries over the dedicated guardian tables of
    the model - so the serializer can answer it on a page without one query
    per row and without one per role.
    """

    def with_visibility(self):
        """The queryset annotated with ``visibility`` (#739).

        Returns:
            the queryset answering ``extras.permissions.Visibility`` per row
        """
        from registry.expressions.visibility import visibility_expression
        return self.annotate(visibility=visibility_expression(self.model))


class WebMapServiceQuerySet(ServiceAlertQuerySetMixin,
                            VisibilityQuerySetMixin, QuerySet):
    def update_candidates(self):
        return self.filter(
            update_candidate_of__isnull=False
        )

    def real_services(self):
        return self.filter(
            update_candidate_of__isnull=True
        )

    def prefetch_whole_service(
        self,
    ) -> "WebMapServiceQuerySet":
        from registry.models.metadata import Style
        from registry.models.service import Layer
        styles_prefetch = Prefetch(
            "styles",
            Style.objects.select_related(
                "legend_url",
                "legend_url__mime_type"
            )
        )

        # the published metadata links of a layer are rendered out of its remote
        # metadata and its publishable metadata relations, see
        # registry.models.service.ServiceElement.published_metadata_links
        metadata_relations_prefetch = Prefetch(
            "metadata_relations",
            queryset=models.MetadataRelation.objects.publishable().select_related(
                "dataset_metadata"
            )
        )

        layer_prefetch = Prefetch(
            "layers",
            Layer.objects.select_related(
                "mptt_parent"
            ).prefetch_related(
                "keywords",
                "reference_systems",
                "remote_metadata",
                metadata_relations_prefetch,
                "time_extents",
                styles_prefetch
            ).annotate(
                sibling_index=SIBLING_INDEX
            )
        )

        return self.select_related(
            "service_contact",
            "metadata_contact"
        ).prefetch_related(
            "operation_urls",
            "keywords",
            layer_prefetch
        )

    def for_update_diff(
        self, update_config=None
    ) -> "WebMapServiceQuerySet":
        """Read plan of the update job which diffs this service against its
        candidate (#1393).

        The update counterpart of ``prefetch_whole_service``, which stays the
        API's view plan: an update reads the element rows for its mapping
        phase (identifiers, tree positions and the parent of an unnamed
        grouping layer) and, for the service itself, only the relations its
        ``update_config`` names — ``update_metadata`` compares exactly those
        against the candidate. The styles, time extents, remote and
        publishable metadata of every element are not read by the update at
        all: the element relations the config names for ``Layer`` are read
        per relation on the mapping rows of ``update_layers``, never on this
        prefetch.
        """
        from registry.models.service import Layer

        config = update_config or {}
        return self.prefetch_related(
            Prefetch(
                "layers",
                Layer.objects.select_related("mptt_parent")
            ),
            *[
                Prefetch(name) for name in configured_relation_fields(
                    self.model, config.get(self.model.__name__, {}))
            ]
        )

    def with_security_information(self) -> "WebMapServiceQuerySet":
        return self.annotate(
            camouflage=Coalesce(
                F("proxy_setting__camouflage"), Value(False)),
            log_response=Coalesce(
                F("proxy_setting__log_response"), Value(False)),
            is_secured=Exists(
                models.AllowedWebMapServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                )
            ),
            is_spatial_secured=Exists(
                models.AllowedWebMapServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                    allowed_area__isnull=False
                )
            )
        )


class WebFeatureServiceQuerySet(ServiceAlertQuerySetMixin,
                                VisibilityQuerySetMixin, QuerySet):
    def prefetch_whole_service(self) -> "WebFeatureServiceQuerySet":
        # the published metadata links of a feature type are rendered out of its remote
        # metadata and its publishable metadata relations, see
        # registry.models.service.ServiceElement.published_metadata_links
        featuretypes = Prefetch(
            "featuretypes",
            queryset=models.FeatureType.objects.prefetch_related(
                "keywords", "output_formats", "reference_systems", "remote_metadata",
                Prefetch(
                    "metadata_relations",
                    queryset=models.MetadataRelation.objects.publishable().select_related(
                        "dataset_metadata"
                    )
                )
            ),
        )
        return self.select_related("service_contact", "metadata_contact").prefetch_related(
            "operation_urls__mime_types", "keywords", featuretypes
        )

    def for_update_diff(
        self, update_config=None
    ) -> "WebFeatureServiceQuerySet":
        """Read plan of the update job which diffs this service against its
        candidate (#1393) — the WFS counterpart of
        :meth:`WebMapServiceQuerySet.for_update_diff`: the feature type rows
        for the mapping phase plus only the service relations the update
        config names; the element relations the config names are read on the
        mapping rows of ``update_featuretypes``, not here.
        """
        config = update_config or {}
        return self.prefetch_related(
            "featuretypes",
            *[
                Prefetch(name) for name in configured_relation_fields(
                    self.model, config.get(self.model.__name__, {}))
            ]
        )

    def with_security_information(self) -> "WebFeatureServiceQuerySet":
        return self.annotate(
            camouflage=Coalesce(
                F("proxy_setting__camouflage"), Value(False)),
            log_response=Coalesce(
                F("proxy_setting__log_response"), Value(False)),
            is_secured=Exists(
                models.AllowedWebFeatureServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                )
            ),
            is_spatial_secured=Exists(
                models.AllowedWebFeatureServiceOperation.objects.filter(
                    secured_service__id__exact=OuterRef("pk"),
                    allowed_area__isnull=False
                )
            )
        )


class CatalogueServiceQuerySet(ServiceAlertQuerySetMixin, QuerySet):
    def prefetch_whole_service(self) -> "CatalogueServiceQuerySet":
        return self.select_related("service_contact", "metadata_contact").prefetch_related(
            "operation_urls__mime_types", "keywords"
        )

    def for_update_diff(
        self, update_config=None
    ) -> "CatalogueServiceQuerySet":
        """Read plan of the update job which diffs this service against its
        candidate (#1393) — the CSW counterpart of
        :meth:`WebMapServiceQuerySet.for_update_diff`: a CSW has no elements
        to map, so the plan carries exactly the service relations the update
        config names.
        """
        config = update_config or {}
        return self.prefetch_related(
            *[
                Prefetch(name) for name in configured_relation_fields(
                    self.model, config.get(self.model.__name__, {}))
            ]
        )


class CatalogueServiceManager(Manager.from_queryset(CatalogueServiceQuerySet), Manager.from_queryset(DefaultHistoryManager)):
    pass


class LayerManager(Manager.from_queryset(LayerQuerySet), DefaultHistoryManager, TreeManager):
    pass
