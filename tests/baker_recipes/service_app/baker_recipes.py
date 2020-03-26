from model_bakery.recipe import Recipe, foreign_key
from service.helper.enums import OGCServiceEnum, OGCServiceVersionEnum, MetadataEnum
from service.models import Metadata, Service, ServiceType, MetadataType
from tests.baker_recipes.structure_app.baker_recipes import superadmin_group


layer_metadatatype = Recipe(
    MetadataType,
    type=MetadataEnum.LAYER
)

featuretype_metadatatype = Recipe(
    MetadataType,
    type=MetadataEnum.FEATURETYPE
)

service_metadatatype = Recipe(
    MetadataType,
    type=MetadataEnum.SERVICE
)

active_wms_service_metadata = Recipe(
    Metadata,
    is_active=True,
    metadata_type=foreign_key(service_metadatatype),
    created_by=foreign_key(superadmin_group),
)

active_wms_layer_metadata = active_wms_service_metadata.extend(
    metadata_type=foreign_key(layer_metadatatype),
)


active_wfs_service_metadata = Recipe(
    Metadata,
    is_active=True,
    metadata_type=foreign_key(service_metadatatype),
    created_by=foreign_key(superadmin_group),
)

active_wfs_featuretype_metadata = active_wfs_service_metadata.extend(
    metadata_type=foreign_key(featuretype_metadatatype),
)

wms_v100_servicetype = Recipe(
    ServiceType,
    name=OGCServiceEnum.WMS,
    version=OGCServiceVersionEnum.V_1_0_0,
)

wfs_v100_servicetype = Recipe(
    ServiceType,
    name=OGCServiceEnum.WFS,
    version=OGCServiceVersionEnum.V_1_0_0,
)

active_root_wms_service = Recipe(
    Service,
    is_active=True,
    is_root=True,
    metadata=foreign_key(active_wms_service_metadata),
    servicetype=foreign_key(wms_v100_servicetype),
    created_by=foreign_key(superadmin_group),

)

active_root_wfs_service = Recipe(
    Service,
    is_active=True,
    is_root=True,
    metadata=foreign_key(active_wfs_service_metadata),
    servicetype=foreign_key(wfs_v100_servicetype),
    created_by=foreign_key(superadmin_group),
)