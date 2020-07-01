from datetime import datetime
from model_bakery import seq
from model_bakery.recipe import Recipe, foreign_key, related
from service.helper.enums import OGCServiceEnum, OGCServiceVersionEnum, MetadataEnum, DocumentEnum
from service.models import Metadata, Service, ServiceType, MetadataType, Layer, FeatureType, Keyword, Category, \
    Document, RequestOperation, MimeType, MetadataOrigin, ProxyLog, Dataset
from tests.baker_recipes.structure_app.baker_recipes import superadmin_group, superadmin_orga

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

wms_v100_service_type = Recipe(
    ServiceType,
    name=OGCServiceEnum.WMS.value,
    version=OGCServiceVersionEnum.V_1_0_0.value,
)

wfs_v100_service_type = Recipe(
    ServiceType,
    name=OGCServiceEnum.WFS.value,
    version=OGCServiceVersionEnum.V_1_0_0.value,
)

active_root_wms_service = Recipe(
    Service,
    is_active=True,
    is_root=True,
    metadata=foreign_key(active_wms_service_metadata),
    service_type=foreign_key(wms_v100_service_type),
    created_by=foreign_key(superadmin_group),
)

active_wms_sublayer = Recipe(
    Layer,
    identifier=seq("Layer"),
    is_active=True,
    is_root=False,
    metadata=foreign_key(active_wms_layer_metadata),
    service_type=foreign_key(wms_v100_service_type),
    created_by=foreign_key(superadmin_group),
    parent_service=foreign_key(active_root_wms_service),
)

active_root_wfs_service = Recipe(
    Service,
    is_active=True,
    is_root=True,
    metadata=foreign_key(active_wfs_service_metadata),
    service_type=foreign_key(wfs_v100_service_type),
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
    contact=foreign_key(superadmin_orga),
)

active_dataset = Recipe(
    Dataset,
    metadata=foreign_key(active_dataset_metadata),
    is_active=True,
    created_by=foreign_key(superadmin_group),
)

capability_document = Recipe(
    Document,
    metadata=foreign_key(active_dataset_metadata),
    created_by=foreign_key(superadmin_group),
    content="<test></test>",
    is_original=True,
    document_type=DocumentEnum.CAPABILITY.value,
)

metadata_document = Recipe(
    Document,
    metadata=foreign_key(active_dataset_metadata),
    created_by=foreign_key(superadmin_group),
    content="<test></test>",
    is_original=True,
    document_type=DocumentEnum.METADATA.value,
)

metadata_origin = Recipe(
    MetadataOrigin,
    name="capabilities"
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