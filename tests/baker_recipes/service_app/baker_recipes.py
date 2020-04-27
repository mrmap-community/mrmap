from model_bakery import seq
from model_bakery.recipe import Recipe, foreign_key
from service.helper.enums import OGCServiceEnum, OGCServiceVersionEnum, MetadataEnum
from service.models import Metadata, Service, ServiceType, MetadataType, Layer, FeatureType, Keyword, Category, Document
from tests.baker_recipes.structure_app.baker_recipes import superadmin_group, superadmin_user

layer_metadatatype = Recipe(
    MetadataType,
    type=MetadataEnum.LAYER.value
)

featuretype_metadatatype = Recipe(
    MetadataType,
    type=MetadataEnum.FEATURETYPE.value
)

service_metadatatype = Recipe(
    MetadataType,
    type=MetadataEnum.SERVICE.value
)

active_wms_service_metadata = Recipe(
    Metadata,
    title=seq("metadata_wms_"),
    is_active=True,
    metadata_type=foreign_key(service_metadatatype),
    created_by=foreign_key(superadmin_group),
)

active_wms_layer_metadata = active_wms_service_metadata.extend(
    metadata_type=foreign_key(layer_metadatatype),
)


active_wfs_service_metadata = Recipe(
    Metadata,
    title=seq("metadata_wfs_"),
    is_active=True,
    metadata_type=foreign_key(service_metadatatype),
    created_by=foreign_key(superadmin_group),
)

active_wfs_featuretype_metadata = active_wfs_service_metadata.extend(
    metadata_type=foreign_key(featuretype_metadatatype),
)

wms_v100_servicetype = Recipe(
    ServiceType,
    name=OGCServiceEnum.WMS.value,
    version=OGCServiceVersionEnum.V_1_0_0,
)

wfs_v100_servicetype = Recipe(
    ServiceType,
    name=OGCServiceEnum.WFS.value,
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

active_wms_root_layer = Recipe(
    Layer,
    is_active=True,
    is_root=True,
    metadata=foreign_key(active_wms_layer_metadata),
    servicetype=foreign_key(wms_v100_servicetype),
    created_by=foreign_key(superadmin_group),
    parent_service=foreign_key(active_root_wms_service),
)

active_wms_sublayer = active_wms_root_layer.extend(
    is_root=False,
)

active_root_wfs_service = Recipe(
    Service,
    is_active=True,
    is_root=True,
    metadata=foreign_key(active_wfs_service_metadata),
    servicetype=foreign_key(wfs_v100_servicetype),
    created_by=foreign_key(superadmin_group),
)

active_wfs_featuretype = Recipe(
    FeatureType,
    is_active=True,
    metadata=foreign_key(active_wfs_featuretype_metadata),
    created_by=foreign_key(superadmin_group),
    parent_service=foreign_key(active_root_wfs_service),
)

keyword = Recipe(
    Keyword,
    keyword=seq("keyword_")
)

category = Recipe(
    Category,
    type=seq("type_"),
    title_locale_1=seq("title_"),
    description_locale_1=seq("desc_"),
    title_EN=seq("title_"),
    description_EN=seq("desc_"),
)

document = Recipe(
    Document,
    related_metadata=foreign_key(active_wms_service_metadata)
)

wms_update_candidate = Recipe(
    Service,
    is_active=False,
    is_root=True,
    metadata=foreign_key(active_wms_service_metadata),
    servicetype=foreign_key(wms_v100_servicetype),
    created_by=foreign_key(superadmin_group),
    is_update_candidate_for=foreign_key(active_root_wms_service),
    created_by_user=foreign_key(superadmin_user),
)

wfs_update_candidate = Recipe(
    Service,
    is_active=False,
    is_root=True,
    metadata=foreign_key(active_wfs_service_metadata),
    servicetype=foreign_key(wfs_v100_servicetype),
    created_by=foreign_key(superadmin_group),
    is_update_candidate_for=foreign_key(active_root_wfs_service),
    created_by_user=foreign_key(superadmin_user),
)
