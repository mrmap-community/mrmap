import uuid

from django.contrib.gis.geos import Polygon

from service.helper.enums import MetadataEnum, OGCOperationEnum, MetadataRelationEnum
from service.helper.epsg_api import EpsgApi
from service.models import Service, Metadata, Layer, Keyword, ReferenceSystem, MetadataRelation, Dimension, MimeType, \
    ServiceUrl
from service.settings import SERVICE_OPERATION_URI_TEMPLATE, SERVICE_METADATA_URI_TEMPLATE, HTML_METADATA_URI_TEMPLATE, \
    ALLOWED_SRS
from structure.models import MrMapGroup, MrMapUser


class OGCLayer:
    def __init__(self, identifier=None, position=0, parent=None, title=None, queryable=False, opaque=False,
                 cascaded=False, abstract=None):
        self.identifier = identifier
        self.position = position
        self.parent = parent
        self.is_queryable = queryable
        self.is_opaque = opaque
        self.is_cascaded = cascaded
        self.title = title
        self.abstract = abstract

        # capabilities
        self.capability_keywords = []
        self.capability_online_resource = None
        self.capability_projection_system = []
        self.capability_scale_hint = {
            "min": 0,
            "max": 0,
        }
        self.capability_bbox_lat_lon = {
            "minx": 0,
            "miny": 0,
            "maxx": 0,
            "maxy": 0,
        }
        self.capability_bbox_srs = {}

        self.format_list = {}
        self.get_capabilities_uri_GET = None
        self.get_capabilities_uri_POST = None
        self.get_map_uri_GET = None
        self.get_map_uri_POST = None
        self.get_feature_info_uri_GET = None
        self.get_feature_info_uri_POST = None
        self.describe_layer_uri_GET = None
        self.describe_layer_uri_POST = None
        self.get_legend_graphic_uri_GET = None
        self.get_legend_graphic_uri_POST = None
        self.get_styles_uri_GET = None
        self.get_styles_uri_POST = None
        self.dimension_list = []
        self.style = None
        self.child_layers = []

        self.iso_metadata = []

    def create_layer_record(self, parent_service: Service, group: MrMapGroup, user: MrMapUser, epsg_api: EpsgApi, parent_layer: Layer=None):
        """ Transforms a OGCWebMapLayer object to Layer model (models.py)

        Args:
            parent_service (Service): The root or parent service which holds all these layers
            group (MrMapGroup): The group that started the registration process
            user (MrMapUser): The performing user
            epsg_api (EpsgApi): A EpsgApi object
            parent_layer (Layer): The parent layer object to this layer
        Returns:
            nothing
        """
        # Metadata
        metadata = self._create_metadata_record(parent_service, group)

        # Layer
        layer = self._create_layer_record(
            metadata,
            parent_service,
            group,
            parent_layer
        )

        # Additional records
        self._create_additional_records(
            metadata,
            layer,
            group,
            epsg_api
        )

        # Final save before continue
        metadata.save()
        layer.save()

        # Continue with child objects
        for child in self.child_layers:
            child.create_layer_record(
                parent_service=parent_service,
                group=group,
                parent_layer=layer,
                user=user,
                epsg_api=epsg_api
            )

    def _create_metadata_record(self, parent_service: Service, group: MrMapGroup):
        """ Creates a Metadata record from the OGCLayer object

        Args:
            self (OGCLayer): The OGCLayer object (result of parsing)
            parent_service (Service): The parent Service object 
            group (MrMapGroup): The creator/owner group
        Returns:
             metadata (Metadata): The persisted metadata object
        """
        metadata = Metadata()
        md_type = MetadataEnum.LAYER.value
        metadata.metadata_type = md_type
        metadata.title = self.title
        metadata.abstract = self.abstract
        metadata.online_resource = parent_service.metadata.online_resource
        metadata.capabilities_original_uri = parent_service.metadata.capabilities_original_uri
        metadata.identifier = self.identifier
        metadata.contact = parent_service.metadata.contact
        metadata.access_constraints = parent_service.metadata.access_constraints
        metadata.is_active = False
        metadata.created_by = group

        # Save metadata to use id afterwards
        metadata.save()

        # create bounding box polygon
        bounding_points = (
            (float(self.capability_bbox_lat_lon["minx"]), float(self.capability_bbox_lat_lon["miny"])),
            (float(self.capability_bbox_lat_lon["minx"]), float(self.capability_bbox_lat_lon["maxy"])),
            (float(self.capability_bbox_lat_lon["maxx"]), float(self.capability_bbox_lat_lon["maxy"])),
            (float(self.capability_bbox_lat_lon["maxx"]), float(self.capability_bbox_lat_lon["miny"])),
            (float(self.capability_bbox_lat_lon["minx"]), float(self.capability_bbox_lat_lon["miny"]))
        )
        metadata.bounding_geometry = Polygon(bounding_points)

        metadata.save()

        return metadata
    
    def _create_layer_record(self, metadata: Metadata, parent_service: Service, group: MrMapGroup, parent_layer: Layer):
        """ Creates a Layer record from the OGCLayer object

        Args:
            metadata (Metadata): The layer's metadata object
            parent_service (Service): The parent Service object
            group (MrMapGroup): The owner/creator group
            parent_layer (Layer): The parent layer object
        Returns:
             layer (Layer): The persisted layer object
        """
        # Layer
        layer = Layer()
        layer.metadata = metadata
        layer.identifier = self.identifier
        layer.service_type = parent_service.service_type
        layer.position = self.position
        layer.parent_layer = parent_layer
        layer.parent_service = parent_service
        layer.is_queryable = self.is_queryable
        layer.is_cascaded = self.is_cascaded
        layer.registered_by = group
        layer.is_opaque = self.is_opaque
        layer.scale_min = self.capability_scale_hint.get("min")
        layer.scale_max = self.capability_scale_hint.get("max")
        layer.bbox_lat_lon = metadata.bounding_geometry
        layer.created_by = group
        layer.published_for = parent_service.published_for
        layer.parent_service = parent_service

        # Save model so M2M relations can be used
        layer.save()

        operation_urls = [
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_CAPABILITIES.value,
                url=self.get_capabilities_uri_GET,
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_CAPABILITIES.value,
                url=self.get_capabilities_uri_POST,
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_FEATURE_INFO.value,
                url=self.get_feature_info_uri_GET,
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_FEATURE_INFO.value,
                url=self.get_feature_info_uri_POST,
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.DESCRIBE_LAYER.value,
                url=self.describe_layer_uri_GET,
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.DESCRIBE_LAYER.value,
                url=self.describe_layer_uri_POST,
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_STYLES.value,
                url=self.get_styles_uri_GET,
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_STYLES.value,
                url=self.get_styles_uri_POST,
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_LEGEND_GRAPHIC.value,
                url=self.get_legend_graphic_uri_GET,
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_LEGEND_GRAPHIC.value,
                url=self.get_legend_graphic_uri_POST,
                method="Post"
            )[0],

            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_MAP.value,
                url=self.get_map_uri_GET,
                method="Get"
            )[0],
            ServiceUrl.objects.get_or_create(
                operation=OGCOperationEnum.GET_MAP.value,
                url=self.get_map_uri_POST,
                method="Post"
            )[0],

        ]

        layer.operation_urls.add(*operation_urls)

        # If parent layer is a real layer, we add the current layer as a child to the parent layer
        if layer.parent_layer is not None:
            layer.parent_layer.child_layers.add(layer)

        if self.style is not None:
            self.style.layer = layer
            self.style.save()

        if parent_service.root_layer is None:
            # no root layer set yet
            parent_service.root_layer = layer
            parent_service.save()

        layer.save()

        return layer
    
    def _create_additional_records(self, metadata: Metadata, layer: Layer, group: MrMapGroup, epsg_api: EpsgApi):
        """ Creates additional records such as Keywords, ReferenceSystems, Dimensions, ...

        Args:
            metadata (Metadata): The layer's metadata object
            layer (Layer): The Layer record object
            group (MrMapGroup): The owner/creator group
            epsg_api (EpsgApi): A epsg_api object
        Returns:

        """
        # Keywords
        for kw in self.capability_keywords:
            keyword = Keyword.objects.get_or_create(keyword=kw)[0]
            metadata.keywords.add(keyword)

        # handle reference systems
        for sys in self.capability_projection_system:
            parts = epsg_api.get_subelements(sys)
            # check if this srs is allowed for us. If not, skip it!
            if parts.get("code") not in ALLOWED_SRS:
                continue
            ref_sys = ReferenceSystem.objects.get_or_create(code=parts.get("code"), prefix=parts.get("prefix"))[0]
            metadata.reference_system.add(ref_sys)

        for iso_md in self.iso_metadata:
            iso_md = iso_md.to_db_model(created_by=group)
            metadata_relation = MetadataRelation()
            metadata_relation.metadata_to = iso_md
            metadata_relation.origin = iso_md.origin
            metadata_relation.relation_type = MetadataRelationEnum.DESCRIBED_BY.value
            metadata_relation.save()
            metadata.related_metadata.add(metadata_relation)

        # Dimensions
        for dimension in self.dimension_list:
            dim = Dimension.objects.get_or_create(
                type=dimension.get("type"),
                units=dimension.get("units"),
                extent=dimension.get("extent"),
            )[0]
            layer.metadata.dimensions.add(dim)
