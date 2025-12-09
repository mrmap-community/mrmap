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


class LanguageChoices(SmartIntegerChoices):
    ger = 1, _("ger")
    en = 2, _("en")


class MetadataCharsetChoices(SmartIntegerChoices):
    UTF8 = 8, _("utf8")


class ReferenceSystemPrefixChoices(TextChoices):
    EPSG = "EPSG"


class UpdateFrequencyChoices(SmartIntegerChoices):
    UNKNOWN = 0, _("unknown")
    ANNUALLY = 1, _("annually")
    BIANNUALLY = 2, _("biannually")
    AS_NEEDED = 3, _("as needed")
    IRREGULAR = 4, _("irregular")
    NOT_PLANNED = 5, _("not planned")
