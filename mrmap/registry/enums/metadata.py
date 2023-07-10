from django.db.models.enums import TextChoices


class CategoryOriginEnum(TextChoices):
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


class MetadataOriginEnum(TextChoices):
    """ Defines origins from where a resource could be coming from

    """
    CAPABILITIES = "Capabilities"
    UPLOAD = "Upload"
    EDITOR = "Editor"
    CATALOGUE = "Catalogue"


class MetadataRelationEnum(TextChoices):
    """ Defines types of metadata relations for MetadataRelation model

    """
    VISUALIZES = "visualizes"
    DESCRIBES = "describes"
    HARVESTED_THROUGH = "harvestedThrough"
    HARVESTED_PARENT = "harvestedParent"
    PUBLISHED_BY = "publishedBy"


class DatasetFormatEnum(TextChoices):
    DATABASE = "Database"
    ESRI_SHAPE = "Esri shape"
    CSV = "CSV"
    GML = "GML"
    GEOTIFF = "GeoTIFF"


class MetadataCharset(TextChoices):
    UTF8 = "utf8"


class MetadataOrigin(TextChoices):
    CAPABILITIES = "capabilities"
    ISO_METADATA = "iso metadata"


class ReferenceSystemPrefixEnum(TextChoices):
    EPSG = "EPSG"
