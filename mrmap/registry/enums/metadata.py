from MrMap.enums import EnumChoice


class CategoryOriginEnum(EnumChoice):
    """ Defines sources for categories
    """
    ISO = "iso"
    INSPIRE = "inspire"

    @classmethod
    def all_values_as_list(cls):
        return [enum.value for enum in cls]

    @classmethod
    def all_names_as_list(cls):
        return [enum.name for enum in cls]


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


class ReferenceSystemPrefixEnum(EnumChoice):
    EPSG = "EPSG"


class HarvestResultEnum(EnumChoice):
    FETCHED = "fetched"  # successfully fetched but not parsed
    INSUFFICIENT_QUALITY = "insufficient quality"  # if catched xml parsing errors
    SUCCESSFULLY = "successfully"  # fetched and parsed without errors
