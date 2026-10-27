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


class MetadataRelationPublicationEnum(SmartIntegerChoices):
    """ Defines how a MetadataRelation contributes to the xml which MrMap publishes.

        The kind is never persisted. It is calculated from the provenance fields
        `origin` and `is_internal` of the relation, see
        :meth:`registry.models.metadata.MetadataRelation.publication_kind`.

        Note: This is no choice of a model field and is only used to report the
        coupling of a relation, thats why the labels are not translated.
    """
    # The relation only documents a link which was found in a imported document. The
    # link it self is stored in the related *RemoteMetadata model and is published
    # through it, the relation adds nothing to the published xml.
    IMPORTED_EVIDENCE = 1, "Imported evidence"
    # The relation was created by a user but is not intended for publication. MrMap
    # knows the coupling, but no client shall see it.
    LOCAL_ONLY = 2, "Local only"
    # The relation was created by a curator and shall be published. It is the only
    # kind which contributes a new node to the published xml.
    CURATED_PUBLICATION = 3, "Curated publication"


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


class MetadataCouplingKindEnum(SmartIntegerChoices):
    """ Defines the kind of a coupling reference which a harvested service
        metadata record advertises in its iso document.

        The kind is part of the evidence: the values of different kinds live in
        different namespaces and shall never be matched against each other.
    """
    # srv:operatesOn/@uuidref: names the file identifier of a metadata record
    UUIDREF = 1, _("Uuid reference")
    # srv:operatesOn/@xlink:href: names the location of a metadata record
    HREF = 2, _("Href reference")
    # srv:SV_CoupledResource/srv:identifier: names the described resource
    IDENTIFIER = 3, _("Identifier reference")
    # srv:SV_CoupledResource/srv:scopedName: names the resource by its scope
    SCOPED_NAME = 4, _("Scoped name reference")
