from django.db.models.enums import TextChoices
from django.utils.translation import gettext_lazy as _
from extras.enums import SmartIntegerChoices


# TODO: use IntegerChoices instead
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


class MetadataOriginEnum(SmartIntegerChoices):
    # TODO: check if this is needed... is it calculable based on relation types (MetadataRelation Model)?
    """ Defines origins from where a resource could be coming from

    """
    CAPABILITIES = 1, _("Capabilities")
    UPLOAD = 2, _("Upload")
    FILE_SYSTEM_IMPORT = 3, _("File System Import")
    EDITOR = 4, _("Editor")
    CATALOGUE = 5, _("Catalogue")


class DatasetFormatEnum(SmartIntegerChoices):
    DATABASE = 1, _("Database")
    ESRI_SHAPE = 2, _("Esri shape")
    CSV = 3, _("CSV")
    GML = 4, _("GML")
    GEOTIFF = 5, _("GeoTIFF")



class ReferenceSystemPrefixChoices(TextChoices):
    EPSG = "EPSG"


class TimeExtentKind(SmartIntegerChoices):
    SINGLE_VALUE = 1, _("Single Value")
    INTERVAL = 2, _("Interval")
    ROLLING = 3, _("Rolling")
