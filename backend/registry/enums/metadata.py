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


class CollectionStepOutcome(TextChoices):
    """The verdict of collecting one reference of a service's capabilities.

    The task which fetches and maps one ``RemoteMetadata`` answer carries
    this outcome so a reader can tell "a record was created" from "the
    document was parsed, but no record could be identified in it" without
    inferring it from the presence of an id (#1261). #1263 stored that
    verdict per reference: the outcome of a registration reference is the
    state and the ``error_kind`` of its work row, and the task answers this
    outcome on top of it.

    Note: This is no choice of a model field and is only used to report the
    outcome of one collected step, thats why the labels are not translated.
    """
    RECORD_CREATED = "record_created", "Record created"
    NO_IDENTIFIABLE_RECORD = (
        "no_identifiable_record", "Parsed, but no identifiable record")


class ReferenceWorkStateEnum(SmartIntegerChoices):
    """The states of one registration reference work row (#1263).

    A row of ``TemporaryMdMetadataFile`` owned by a background process is a
    disposable work item, not a ledger: the successful import deletes it, so
    there is no ``SUCCEEDED`` state - the absence of the row is the success.
    A delivery moves PENDING (or, for an explicitly authorized retry,
    FAILED) to LEASED under a claim token; the decided failure keeps the row
    as LEASED's terminal twin FAILED, with the error recorded on it, until a
    retry claims it again or the owning process is purged.

    Harvesting rows never read these states: that flow keeps deciding by
    ``has_import_error`` and its own chord (#1237 semantics stay).
    """
    PENDING = 0, _("pending")
    LEASED = 1, _("leased")
    # named apart from the update job's "failed": the catalog translates the
    # bare word into that flow's sentence and one msgid cannot serve both
    FAILED = 2, _("reference failed")


class ReferenceErrorKind(TextChoices):
    """Machine-readable kinds of a failed reference (#1263).

    The failure of one work row is stored as one of these kinds beside its
    error text, so #1259's summary and #1265's retry screen can tell a
    document which was never answered from one which carries no record
    without reading free text. No kind fabricates a record identifier: the
    kinds name what failed, never what was created.

    Note: This is no choice of a model field of a translated form - the kind
    is an interface between machines; the labels are not translated.
    """
    FETCH_TIMEOUT = "fetch_timeout", "Server did not answer"
    FETCH_UNREACHABLE = "fetch_unreachable", "Server not reachable"
    NO_CONTENT = "no_content", "Server answered without a document"
    NO_IDENTIFIABLE_RECORD = (
        "no_identifiable_record", "Document carries no identifiable record")
    UNSUPPORTED_KIND = (
        "unsupported_kind", "Document kind is not supported")
    IMPORT_FAILED = "import_failed", "Import of the document failed"


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
