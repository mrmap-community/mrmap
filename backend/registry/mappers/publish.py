"""The publish seam of the metadata editor (#1244): a committed row IS its document.

Atomic publishing was decided on the review of the design document (decision 1
of §7, PR #1238): in v1 a successful, validated save is the publish - model
fields and the regenerated ``xml_backup_file`` commit together or not at all,
and after the commit the CSW serves exactly what was saved. There is no draft
document, no editorial state column and no second state this module
distinguishes: the document it builds is built FROM the row, so the served
document and the stored record can only ever disagree while a transaction is
still running.

The one seam, both directions:

* :func:`build_resulting_document` answers the document a record's stored
    fields would serve - the record's current document with the row's mapped
    values written over it through the write mapper of #1242 (unmapped content
    carried through byte for byte), or, for a record no document carries yet,
    a skeleton seed of its kind which the write mapper fills like every other
    document. Validation (#1243) evaluates THIS construction before the save;
    publishing persists THESE bytes after it - one construction, no second
    interpretation layer (§5 of the design document).
* :func:`publish_document` attaches the answer to the record inside the
    caller's transaction. The caller must be inside a transaction (the
    ``create``/``update`` of :class:`registry.serializers.metadata.
    RecordWriteSerializerMixin` open one): the assignment makes the file name
    join the next ``save()`` of the row, so document and fields land in one
    commit. On rollback the written file stays as unreferenced garbage of the
    media storage and the row keeps pointing at the old document - "a rejected
    write changes nothing" holds for everything this system serves.

Concurrency is last-write-wins (decision 6 of §7): no lock is taken here, no
revision token is answered; the last committed publish is the document.

The values the document is written from come from the ROW, not the payload:
fields the model maintains itself - the bumped ``date_stamp`` of an editor
save, the server-assigned ``file_identifier`` - travel with it, and a record
whose row and document had drifted apart is healed towards the row, which is
what "search/CSW serve exactly the saved content" means. Fields the write
mapper can not write back (bounding geometry, time extents, the citation
identifier - #1242 named them) are refused as WRITES by
:func:`non_roundtrippable_fields` instead of being committed into the row
while the document silently keeps its old value.
"""

from logging import Logger

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.fields.related_descriptors import ManyToManyDescriptor
from lxml import etree

from registry.exceptions.metadata import PublishRefused
from registry.mappers.configs import XPATH_MAP
from registry.mappers.factory import MDMetadataXmlMapper
from registry.mappers.persistence.custom import (
    METADATA_RECORD_TYPE_KEYS, XML_BACKUP_NAME)
from registry.mappers.rules import OVERLAYABLE_FIELDS, copy_record, \
    overlay_write_values
from registry.mappers.xml_mapper import is_value_spec

logger: Logger = settings.ROOT_LOGGER

#: the ``codeList`` the mapped corpus and the charset predicate of the configs
#: cite for ``MD_ScopeCode``; normative codelist reference text, not a network
#: endpoint the code ever calls
SCOPE_CODE_LIST = ("http://wis.wmo.int/2011/schemata/iso19139_2007/schema/"  # NOSONAR normative WMO/ISO 19139 codelist reference, written as the codeList attribute of the mapped document and matched literally - never requested over the network
                   "resources/Codelist/ML_gmxCodelists.xml#MD_ScopeCode")


def record_kind(record) -> str:
    """The mapping kind of a record: "dataset", "service" or "application".

    One derivation for all three uses: the provenance key of the persistence
    (#976), the ``hierarchyLevel`` a document names the kind with, and the key
    of the config table are the same string.
    """
    kind = METADATA_RECORD_TYPE_KEYS.get(type(record).__name__)
    if kind is None:
        raise PublishRefused(
            f"{type(record).__name__} is not a metadata record kind")
    return kind


def seed_document(kind: str) -> bytes:
    """The minimal document of a record the editor created from nothing.

    A skeleton MD_Metadata of the kind - namespaces of the config on the root,
    the ``hierarchyLevel`` which identifies it, and the header nodes the write
    mapper can not create itself (the ``dateStamp`` path names its value node
    through a `*[self::...]` step, #1242's write can only fill it) - and
    nothing else: every element the record's values carry is created by the
    write mapper at the position its element order table names, exactly like
    it creates them in a harvested document. The header texts are placeholders
    which :func:`_force_header` overwrites in the same construction. Template
    administration is a decided v2 epic (decision 5 of §7); this seed is not a
    template, it is what lets the one write mapper answer a document for a
    record which has never had one.
    """
    mapping = MDMetadataXmlMapper._select_mapping(kind)
    nsmap = dict(mapping["_namespaces"])
    gmd = nsmap["gmd"]
    gco = nsmap["gco"]
    root = etree.Element(f"{{{gmd}}}MD_Metadata", nsmap=nsmap)
    identifier = etree.SubElement(root, f"{{{gmd}}}fileIdentifier")
    etree.SubElement(identifier, f"{{{gco}}}CharacterString").text = "seed"
    stamp = etree.SubElement(root, f"{{{gmd}}}dateStamp")
    # parseable placeholder: string_to_datetime reads it, _force_header
    # replaces the text with the row's stamp before a byte of it is served
    etree.SubElement(stamp, f"{{{gco}}}DateTime").text = "1970-01-01T00:00:00"
    level = etree.SubElement(root, f"{{{gmd}}}hierarchyLevel")
    scope = etree.SubElement(level, f"{{{gmd}}}MD_ScopeCode")
    scope.set("codeList", SCOPE_CODE_LIST)
    scope.set("codeListValue", kind)
    if kind == "application":
        # the application config reads identification values through
        # `identificationInfo/*` - a wildcard the write can not create; the
        # container of the corpus' application documents (#1242 round-trips
        # gdi-de-01.xml) is an MD_DataIdentification, so the seed carries it
        identification = etree.SubElement(
            root, f"{{{gmd}}}identificationInfo")
        etree.SubElement(identification, f"{{{gmd}}}MD_DataIdentification")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def _stored_document(record):
    """The bytes of the record's stored document, or None.

    None answers for "this deployment holds no readable document for the
    record": an empty file field and a file the storage does not carry are the
    same thing to the publish - the document arrives from the row now.
    """
    if not record.xml_backup_file:
        return None
    try:
        content = record.xml_backup
    except (OSError, ValueError):
        return None
    return content or None


def _row_values(record) -> dict:
    """The record's mapped field values, in the shape the overlay converts.

    The row, not the payload, is asked: after the save the payload and the row
    agree anyway, and this also carries what the model set itself during the
    save. A foreign key which points nowhere and an empty collection answer
    "not written" (None resp. [] are the write mapper's own "leave it" values);
    ``file_identifier`` and ``date_stamp`` are forced separately because they
    are not in :data:`OVERLAYABLE_FIELDS` - their document state is their own
    until the publish stamps the row's values in.
    """
    values = {}
    for name in OVERLAYABLE_FIELDS:
        descriptor = getattr(type(record), name, None)
        if descriptor is None:
            # the kind's model does not carry the field at all (a service
            # record names no dataset contact)
            continue
        if isinstance(descriptor, ManyToManyDescriptor):
            values[name] = list(getattr(record, name).all())
            continue
        try:
            values[name] = getattr(record, name)
        except ObjectDoesNotExist:
            values[name] = None
    return values


def _force_header(values: dict, record):
    """The document names the record the row names: identifier and stamp.

    ``file_identifier`` is unique per record and ``date_stamp`` is the value
    the harvest overwrite gate of #1244 compares - a served document which
    still carried the previous stamp after a committed bump would tell the
    next catalogue response that the old document is the newer answer.
    """
    values["file_identifier"] = str(record.file_identifier)
    values["date_stamp"] = record.date_stamp


def _locate_record(records, record):
    """The index of the node this record stands for, or a refusal.

    Validation needs THE node; guessing it among several or answering for
    none is the disconnected assessment the readiness clarification refuses
    (the posture #1243 pinned on the endpoint).
    """
    model_label = (f"{record._meta.app_label}."
                   f"{record.__class__.__name__}")
    file_identifier = str(record.file_identifier)
    positions = [
        index for index, candidate in enumerate(records)
        if candidate.get("model") == model_label
        and str(candidate["values"].get("file_identifier") or "").strip()
        == file_identifier
    ]
    if len(positions) != 1:
        logger.error(
            "record %s does not appear exactly once in its own document "
            "(%d matching nodes of %d)", record.pk, len(positions),
            len(records))
        raise PublishRefused(
            f"the record appears {len(positions)} times in its own document")
    return positions[0]


def build_resulting_document(record, attrs=None,
                             seed_missing=True) -> bytes | None:
    """The document this record's stored fields would serve, as bytes.

    Answers None only for the ``seed_missing=False`` posture over a record
    without a readable stored document; with the default the seed guarantees
    a document for every record.

    Args:
        record: the (saved) metadata record
        attrs: the validated payload of the write, overlaid AFTER the row
            values - during validation the record instance still holds the
            pre-save state and the payload is what the save WOULD change
        seed_missing: when False, a record without a readable stored document
            answers None instead of being built from the skeleton seed - the
            #1243 posture that document rules have nothing to govern over a
            record which serves no document yet (a POST, or a legacy record
            whose file the editor never touched). The publish itself always
            seeds: after #1244 every record which goes through the write path
            ends up with the document the CSW needs to serve it.

    Raises:
        PublishRefused: when the document can not be derived - fail-closed,
            never a write whose served document is unknown.
    """
    kind = record_kind(record)
    content = _stored_document(record)
    seeded = content is None
    if seeded:
        if not seed_missing:
            return None
        content = seed_document(kind)
    try:
        records = MDMetadataXmlMapper.extract_mapped_values(content)
    except Exception:
        logger.exception(
            "the document of record %s can not be mapped for the publish",
            record.pk)
        raise PublishRefused("the stored document can not be mapped")
    # the seed carries exactly one node and nothing claims an identity in it
    # yet - the record's own identity is written into it with the header
    position = 0 if seeded else _locate_record(records, record)
    entry = copy_record(records[position])
    overlay_write_values(entry["values"], _row_values(record))
    if attrs:
        overlay_write_values(entry["values"], attrs)
    _force_header(entry["values"], record)
    records[position] = entry
    try:
        document, warnings = MDMetadataXmlMapper.write_mapped_records(
            content, records)
    except Exception:
        logger.exception(
            "the write mapper refused the resulting document of record %s",
            record.pk)
        raise PublishRefused("the write mapper refused the document")
    for warning in warnings:
        logger.debug("write mapper: record %s: %s", record.pk, warning)
    return document


def publish_document(record, attrs=None):
    """Regenerate the record's document from its row and attach it, unsaved.

    Assigns the document as an uncommitted file: the next ``save()`` commits
    it to storage and writes its name into the same statement - the pattern
    the harvesting persistence has used for one write per record since #858.
    ``mark_customized=False`` because THIS write is the publishing process,
    not the editor's field write: the flag and the stamp bump already happened
    with the row save inside the same transaction, and a second bump would
    drift the document off the stamp it carries.
    """
    document = build_resulting_document(record, attrs)
    record.xml_backup_file = ContentFile(document, name=XML_BACKUP_NAME)
    record.save(mark_customized=False)
    return record


def _entry_writable(entry) -> bool:
    """Whether the write mapper of #1242 can write one config entry back.

    One derivation from the configs, not a second list to maintain: a plain
    path writes; a dict needs its reverse representation (a
    ``_reverse_parser``, or per-field paths for a related row); a value spec
    has no model to write from at all.
    """
    if isinstance(entry, str):
        return True
    if is_value_spec(entry) or not isinstance(entry, dict):
        return False
    if "_model" in entry:
        return bool(entry.get("_base_xpath")) and bool(
            entry.get("fields") or entry.get("_reverse_parser"))
    return bool(entry.get("_reverse_parser"))


def non_roundtrippable_fields(model, field_names) -> set:
    """The writable serializer fields which no document can carry back.

    The readiness clarification of #1244 (2026-11-12): no enabled public
    write path may leave model fields, ``xml_backup_file`` and the CSW output
    out of sync. A field the configs READ from the document but the write
    mapper can not WRITE (bounding geometry, time extents, the citation
    identifier of #1242's TODOs) would do exactly that, so a payload naming
    one is refused with the same posture as a rule set this version can not
    evaluate: refusing is the only answer which never serves a stale value.

    Args:
        model: the record model of the serializer
        field_names: the names the serializer offers; the caller hands the
            non-read-only ones, the read-only pinning of #1240 refuses the
            rest with its own message
    """
    kind = METADATA_RECORD_TYPE_KEYS.get(model.__name__)
    if kind is None:
        return set()
    spec = XPATH_MAP[("ISO", kind)][kind]["fields"]
    not_writable = {name for name, entry in spec.items()
                    if not _entry_writable(entry)}
    return not_writable & set(field_names)
