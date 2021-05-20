from MrMap.enums import EnumChoice


class MetadataOriginEnum(EnumChoice):
    """ Defines origins from where a resource could be coming from

    """
    CAPABILITIES = "Capabilities"
    UPLOAD = "Upload"
    EDITOR = "Editor"
    CATALOGUE = "Catalogue"


class MetadataRelationEnum(EnumChoice):
    """ Defines types of metadata relations for MetadataRelation model

    """
    VISUALIZES = "visualizes"
    DESCRIBES = "describes"
    HARVESTED_THROUGH = "harvestedThrough"
    HARVESTED_PARENT = "harvestedParent"
    PUBLISHED_BY = "publishedBy"


class DatasetFormatEnum(EnumChoice):
    DATABASE = "Database"
    ESRI_SHAPE = "Esri shape"
    CSV = "CSV"
    GML = "GML"
    GEOTIFF = "GeoTIFF"


class MetadataCharset(EnumChoice):
    UTF8 = "utf8"


class MetadataOrigin(EnumChoice):
    CAPABILITIES = "capabilities"
    ISO_METADATA = "iso metadata"
