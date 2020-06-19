from datetime import datetime

from model_bakery import seq
from model_bakery.recipe import Recipe, foreign_key, related
from service.helper.enums import OGCServiceEnum, OGCServiceVersionEnum, MetadataEnum
from service.models import Metadata, Service, ServiceType, MetadataType, Layer, FeatureType, Keyword, Category, \
    Document, RequestOperation, MimeType, MetadataOrigin, ProxyLog
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

dataset_metadatatype = Recipe(
    MetadataType,
    type=MetadataEnum.DATASET.value
)

mimetype = Recipe(
    MimeType,
    mime_type="image/png"
)

active_wms_service_metadata = Recipe(
    Metadata,
    title=seq("metadata_wms_"),
    identifier=seq("metadata_wms"),
    is_active=True,
    metadata_type=foreign_key(service_metadatatype),
    created_by=foreign_key(superadmin_group),
    formats=related(mimetype),
)

active_wms_layer_metadata = active_wms_service_metadata.extend(
    metadata_type=foreign_key(layer_metadatatype),
    identifier=seq("metadata_wms_layer"),
    formats=related(mimetype),
)


active_wfs_service_metadata = Recipe(
    Metadata,
    title=seq("metadata_wfs_"),
    identifier=seq("metadata_wfs"),
    is_active=True,
    metadata_type=foreign_key(service_metadatatype),
    created_by=foreign_key(superadmin_group),
    formats=related(mimetype),
)

active_wfs_featuretype_metadata = active_wfs_service_metadata.extend(
    metadata_type=foreign_key(featuretype_metadatatype),
    identifier=seq("metadata_wfs_featuretype"),
    formats=related(mimetype),
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

active_wms_sublayer = Recipe(
    Layer,
    identifier=seq("Layer"),
    is_active=True,
    is_root=False,
    metadata=foreign_key(active_wms_layer_metadata),
    servicetype=foreign_key(wms_v100_servicetype),
    created_by=foreign_key(superadmin_group),
    parent_service=foreign_key(active_root_wms_service),
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

active_dataset_metadata = Recipe(
    Metadata,
    title=seq("metadata_dataset_"),
    identifier=seq("metadata_dataset_"),
    is_active=True,
    metadata_type=foreign_key(dataset_metadatatype),
    created_by=foreign_key(superadmin_group),
)

document = Recipe(
    Document,
    related_metadata=foreign_key(active_dataset_metadata),
    created_by=foreign_key(superadmin_group),
    original_capability_document="<test></test>",
    current_capability_document="<test></test>",
    dataset_metadata_document="<test></test>",
    service_metadata_document="<test></test>",
)

metadata_origin = Recipe(
    MetadataOrigin,
)

operation = Recipe(
    RequestOperation,
)

proxy_log = Recipe(
    ProxyLog,
    metadata=foreign_key(active_wms_service_metadata),
    operation="GetMap",
    timestamp=datetime.now()
)