"""The publish seam of the metadata editor (#1244): a committed row IS its document.

Atomic publishing was decided on the review of the design document (decision 1
of §7, PR #1238): in v1 a successful, validated save is the publish - model
fields and the regenerated ``xml_backup_file`` commit together or not at all,
and after the commit the CSW serves exactly what was saved. There is no draft
document, no editorial state column and no second state this module
distinguishes: the document it builds is built FROM the row, so the served
document and the stored record can only ever disagree while a transaction is
still running.

The one seam, every direction:

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
* the raw write of #1247 goes the third way: the editor submits a document
    and :func:`build_source_document` validates THAT document against the
    record - the document is the source and the row's mapped values follow it
    (:func:`publish_source_document`). The same :func:`_force_header` keeps
    the document's ``fileIdentifier`` and ``dateStamp`` on the row's terms,
    so even the escape hatch can not serve a document which disagrees with
    the record it stands for.

Concurrency is last-write-wins (decision 6 of §7): no lock is taken here, no
revision token is answered; the last committed publish is the document.

The values the document is written from come from the ROW, not the payload:
fields the model maintains itself - the bumped ``date_stamp`` of an editor
save, the server-assigned ``file_identifier`` - travel with it, and a record
whose row and document had drifted apart is healed towards the row, which is
what "search/CSW serve exactly the saved content" means. Fields the write
mapper can not write back (the citation identifier - #1242 named it;
the extent fields of the same TODO list got their reverse parsers in
#1246) are refused as WRITES by
:func:`non_roundtrippable_fields` instead of being committed into the row
while the document silently keeps its old value.
"""

from logging import Logger

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, models
from django.db.models.fields.related_descriptors import ManyToManyDescriptor
from lxml import etree
from lxml.etree import XMLSyntaxError

from registry.exceptions.metadata import PublishRefused
from registry.mappers.configs import XPATH_MAP
from registry.mappers.factory import MDMetadataXmlMapper
from registry.mappers.parsers.value import string_to_datetime
from registry.mappers.persistence.custom import (
    METADATA_RECORD_TYPE_KEYS, XML_BACKUP_NAME)
from registry.mappers.rules import OVERLAYABLE_FIELDS, copy_record, \
    overlay_write_values
from registry.mappers.xml_mapper import is_value_spec
from registry.models.metadata import (IsoCategory, Keyword, Language,
                                      MetadataContact, ReferenceSystem)

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


#: the scalar fields the raw-XML write of #1247 re-extracts from a submitted
#: document into the row: the form-mapped columns of
#: :data:`registry.mappers.rules.OVERLAYABLE_FIELDS` which are plain columns;
#: the relation names are handled by their own lookup below.
SOURCE_SCALAR_FIELDS = ("title", "abstract", "charset",
                        "update_frequency_code", "access_constraints",
                        "equivalent_scale", "ground_res")

#: the contact FKs of the record kinds, by the name the configs answer
_SOURCE_CONTACT_FIELDS = ("metadata_contact", "dataset_contact",
                          "application_contact")


def _contact_key_fields() -> tuple:
    """The columns a MetadataContact row is identified by.

    Derived from the model's own unique constraint ("we store only atomic
    contact records, identified by all fields") - not kept as a second list.
    """
    for constraint in MetadataContact._meta.constraints:
        if isinstance(constraint, models.UniqueConstraint):
            return tuple(constraint.fields)
    return ()


def _contact_row_for(current, contact_values: dict):
    """The MetadataContact row a document's contact dict names.

    The document speaks the four mapped CI_ResponsibleParty values; a row is
    identified by the full constraint tuple, so the lookup carries the mapped
    values plus the empty default the other columns carry. A current FK which
    agrees on every mapped value is KEPT: the document can not speak the
    other columns, and pointing the record at a fresh row would drop the
    address detail a harvest parsed beside the mapped four.
    """
    if not isinstance(contact_values, dict):
        return None
    lookup = {field: str(contact_values.get(field) or "")
              for field in _contact_key_fields()}
    mapped = ("name", "person_name", "phone", "email")
    if current is not None and all(
            str(getattr(current, field, "") or "") == lookup.get(field)
            for field in mapped):
        return current
    contact = MetadataContact.objects.filter(**lookup).first()
    if contact is not None:
        return contact
    try:
        return MetadataContact.objects.create(**lookup)
    except IntegrityError:
        # a concurrent writer created the same row meanwhile: take theirs
        return MetadataContact.objects.filter(**lookup).first()


def _choice_rows(model, rows, key: str):
    """The lookup-table rows one extracted collection names by its key.

    Entries which name no value are skipped - a row which names nothing
    keeps the record's current collection instead of crashing the write.
    """
    rows_of = []
    for entry in rows or []:
        if not isinstance(entry, dict):
            continue
        value = entry.get(key)
        if value is None:
            continue
        row, _ = model.objects.get_or_create(**{key: value})
        rows_of.append(row)
    return rows_of


#: the m2m collections answered by the lookup tables, with the key an
#: extracted entry names its value by
_CHOICE_COLLECTIONS = {
    "keywords": (Keyword, "keyword"),
    "languages": (Language, "value"),
    "categories": (IsoCategory, "value"),
}


def _reference_system_rows(entries):
    """The rows the extracted reference systems name, prefix and code.

    An entry which names neither is not a reference system and is skipped;
    the pair the document names is the identity of the row, so a repeated
    extraction of the same document takes the row back.
    """
    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        row, _ = ReferenceSystem.objects.get_or_create(
            prefix=entry.get("prefix") or "",
            code=entry.get("code") or "")
        rows.append(row)
    return rows


def _reextract_scalars(record, values):
    """The scalar columns the document names, shapes the column can hold."""
    for name in SOURCE_SCALAR_FIELDS:
        value = values.get(name)
        if value is None or isinstance(value, (list, dict)):
            continue
        setattr(record, name, value)


def _reextract_contacts(record, values):
    """The contact columns, from the row which already says the same."""
    for name in _SOURCE_CONTACT_FIELDS:
        if name not in values:
            continue
        contact = _contact_row_for(getattr(record, name, None),
                                   values[name])
        if contact is not None:
            setattr(record, name, contact)


def _reextract_collections(record, values):
    """The m2m collections the document names, lookup rows resolved."""
    for name in ("keywords", "languages", "categories", "reference_systems"):
        rows_of = values.get(name)
        if not isinstance(rows_of, list) or not hasattr(record, name):
            # not a collection this record kind carries (the service record
            # names no categories) or the document names none
            continue
        if name == "reference_systems":
            record.reference_systems.set(_reference_system_rows(rows_of))
            continue
        model, key = _CHOICE_COLLECTIONS[name]
        getattr(record, name).set(_choice_rows(model, rows_of, key))


def _reextract_into_row(record, values: dict):
    """Write what the submitted document names into the record's row (#1247).

    The inverse of the form write: the fields the editor maps take the value
    the DOCUMENT names; a field the document leaves out keeps the row's value
    (that is the rule the screen states: the next form save regenerates the
    mapped elements from the database, so a left-out element returns from the
    value which survived here). ``file_identifier`` and ``date_stamp`` are
    never re-extracted: their row state is the record's identity and the
    editor stamp of this save, and the header force wrote the ROW's values
    into the document, not the other way. A value whose shape the column can
    not hold (the epic #669 structures the configs read but no record column
    carries) is skipped for the same reason the form write refuses it.
    """
    _reextract_scalars(record, values)
    _reextract_contacts(record, values)
    _reextract_collections(record, values)


def _assert_located_date_stamp(document: bytes, record):
    """The tree-level header guard: THIS record's node names a dateStamp.

    A value check can not do this: :func:`string_to_datetime` raises on
    garbage and on nothing, and the mapping pipeline catches that to answer
    the CURRENT TIME for the failed field — a stripped or corrupt dateStamp
    node therefore extracts as a perfectly plausible stamp (observed on the
    first CI run of #1247). Only the located node itself tells whether the
    curator's document names a stamp the header force can write into.
    """
    try:
        root = etree.fromstring(document)
    except XMLSyntaxError:
        raise PublishRefused("the submitted document is not well-formed XML")
    nodes = [
        element for element in root.iter()
        if isinstance(element.tag, str)
        and etree.QName(element).localname == "MD_Metadata"
        and "".join(element.xpath(
            "./*[local-name()='fileIdentifier']//text()")).strip()
        == str(record.file_identifier)
    ]
    if len(nodes) != 1:
        raise PublishRefused(
            "the submitted document does not carry this record exactly once")
    stamps = nodes[0].xpath(
        "./*[local-name()='dateStamp']/*[local-name()='DateTime'"
        " or local-name()='Date']/text()")
    text = next((stamp for stamp in stamps if stamp and stamp.strip()), None)
    if text is None:
        raise PublishRefused(
            "the submitted document carries no dateStamp node")
    try:
        string_to_datetime(None, text.strip())
    except ValueError:
        raise PublishRefused(
            "the dateStamp of the submitted document is not a parseable date")


def build_source_document(record, document: bytes):
    """The submitted raw document with the record's header written into it.

    The raw write of #1247 makes the SUBMITTED document the source: unlike
    :func:`build_resulting_document` nothing is overlaid from the row onto
    it, and its mapped values flow the other way, into the row (see
    :func:`publish_source_document`). Three things keep the identity rules of
    the corpus intact, all of them the fail-closed posture of the form write:

    * the record must appear in the submitted document EXACTLY ONCE - the
      same :func:`_locate_record` the publish asks, so a document naming
      another record (or this one twice, or not at all) is refused;
    * the located node must name its ``fileIdentifier`` and carry a parseable
      ``dateStamp``: the write mapper can FILL those header nodes but never
      CREATE them (#1242), and without them the identity and the stamp of
      the record could not be written into the document it is served as. The
      dateStamp is checked on the NODE, not on the extracted value: the
      extractor answers a missing node with the current time rather than with
      nothing (its parse-failure fallback), so only the tree tells whether the
      curator's document names a stamp at all;
    * the header then becomes the ROW's - :func:`_force_header` with the
      row's ``file_identifier`` and the ``date_stamp`` the editor save
      bumped - so the served document can never disagree with the row it
      stands for, the invariant of this whole module.

    Returns:
        (bytes, dict): the document as the publish will store it, and the
        values extracted from the SUBMITTED document (before the header
        force) - the re-extraction source for the row.

    Raises:
        PublishRefused: when the document can not become this record's
            source document - fail-closed, never a write whose served
            document is unknown.
    """
    kind = record_kind(record)
    try:
        records = MDMetadataXmlMapper.extract_mapped_values(document)
    except Exception:
        logger.exception(
            "a submitted source document for record %s (%s) can not be "
            "mapped", record.pk, kind)
        raise PublishRefused("the submitted document can not be mapped")
    position = _locate_record(records, record)
    extracted = copy_record(records[position])["values"]
    if not str(extracted.get("file_identifier") or "").strip():
        raise PublishRefused(
            "the submitted document names no fileIdentifier")
    _assert_located_date_stamp(document, record)
    entry = copy_record(records[position])
    _force_header(entry["values"], record)
    records[position] = entry
    try:
        published, warnings = MDMetadataXmlMapper.write_mapped_records(
            document, records)
    except Exception:
        logger.exception(
            "the write mapper refused the submitted source document of "
            "record %s", record.pk)
        raise PublishRefused("the write mapper refused the submitted "
                             "document")
    for warning in warnings:
        logger.debug("write mapper: record %s: %s", record.pk, warning)
    return published, extracted


def publish_source_document(record, document: bytes, values: dict):
    """Store the validated source document and re-extract its values (#1247).

    The write of the document itself: the bytes are the ones validation
    accepted, header included - what the rules were run over is what gets
    served. Like :func:`publish_document` the assignment joins the next
    ``save()`` of the row, so document and re-extracted values commit in one
    statement inside the caller's transaction; ``mark_customized=False``
    because the flag and the stamp bump are the row save of the write
    itself (#1247 AC 4), this is the publishing half. On rollback the
    written file is unreferenced garbage of the media storage, never served.
    """
    _reextract_into_row(record, values)
    record.xml_backup_file = ContentFile(document, name=XML_BACKUP_NAME)
    record.save(mark_customized=False)
    return record


def non_roundtrippable_fields(model, field_names) -> set:
    """The writable serializer fields which no document can carry back.

    The readiness clarification of #1244 (2026-11-12): no enabled public
    write path may leave model fields, ``xml_backup_file`` and the CSW output
    out of sync. A field the configs READ from the document but the write
    mapper can not WRITE (the citation identifier of #1242's TODOs) would do
    exactly that, so a payload naming one is refused with the same posture as
    a rule set this version can not evaluate: refusing is the only answer
    which never serves a stale value.

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
