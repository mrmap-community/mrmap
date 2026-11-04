from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import ForeignKey
from django.db.models.fields.generated import GeneratedField

# the name the xml backup of an imported record is stored under
XML_BACKUP_NAME = 'md_metadata.xml'


def _defaults_of_instance(instance):
    """The field values of a parsed instance, to create or update the db record
    with.

    A foreign key is read by its key column. The relation descriptor of an
    instance which was only parsed means a query for the related record and
    raises RelatedObjectDoesNotExist if the mapper did not set the key at all,
    which hides the field that is really missing.

    A column the database maintains is left out entirely: the parsed instance only
    carries the default of the field, so sending it would reset what the database
    keeps in sync.
    """
    maintained = getattr(instance.__class__, "db_maintained_fields", ())
    defaults = {}
    for field in instance.__class__._meta.concrete_fields:
        if field.name == "file_identifier" or isinstance(field, GeneratedField):
            continue
        if field.name in maintained:
            continue
        is_foreign_key = isinstance(field, ForeignKey)
        attribute = field.attname if is_foreign_key else field.name
        value = getattr(instance, attribute)
        if is_foreign_key and value is None:
            # the mapper may have set a related instance which is not stored yet
            attribute = field.name
            value = getattr(instance, attribute, None)
        if value is None and is_foreign_key and not field.null:
            raise ValueError(
                f"{instance.__class__.__name__} '{instance.file_identifier}' has no '{field.name}'. The source document does not contain the element this field is mapped from.")
        defaults[attribute] = value
    return defaults


def _write_values_of(instance, handler, model_key):
    """The column values a parsed record is written with.

    Two columns are left out of that set because the document says nothing about
    them: the xml backup, which is the document itself and therefore written with
    the record, and `is_customized`, which says whether an editor changed the
    record - a harvest which sets the flag or resets it tells a lie either way
    (#858).
    """
    values = _defaults_of_instance(instance)
    values.pop("xml_backup_file", None)
    values.pop("is_customized", None)
    for field, value in handler.defaults.get(model_key, {}).items():
        values.setdefault(field, value)
    return values


def _apply_values(record, values):
    """Copy the parsed column values onto the row which was fetched for them.

    The primary key is skipped: the key of the parsed but unsaved instance is a
    fresh uuid which no row carries, so copying it would move the fetched row
    away instead of updating it (#811).
    """
    pk_name = record._meta.pk.name
    for field, value in values.items():
        if field != pk_name:
            setattr(record, field, value)


def _save_record(record, backup, change_reason):
    """Save a record once, with its xml backup and its history reason.

    The backup is assigned as an uncommitted file: `Model.save()` commits it to
    storage and puts its name into the same statement, which is why storing the
    document costs no second write of the row. It is written inside the
    transaction of the import on purpose - a document which cannot be stored must
    not leave a record behind which points at a file that never arrived.

    The reason is carried on the instance, which is how simple_history fills the
    history row it writes with this same statement; naming it afterwards means
    updating that row a second time (#858). `mark_customized` is off because this
    write is the harvesting process and not an editor.
    """
    record.xml_backup_file = ContentFile(backup, name=XML_BACKUP_NAME)
    record._change_reason = change_reason
    record.save(mark_customized=False)
    return record


def _record_of(model, file_identifier):
    """The row of a file identifier, locked for the transaction reading it."""
    return model.objects.select_for_update().filter(
        file_identifier=file_identifier).first()


def get_or_create_metadatarecord(instances, handler):
    """Look every parsed metadata record up and write it once.

    A record which no row carries yet is inserted, a record the catalogue
    republished with a newer date stamp is updated in place, and a record the
    catalogue did not change is left alone: its row is not written at all. The
    xml backup of the document and the reason of the history row travel with that
    one write, which is what makes an import cost one row write instead of two or
    three (#858).

    Args:
        instances: the parsed instances of this model
        handler: the persistence handler which persists the whole document

    Returns:
        dict: the stored records by the key of the parsed instance
    """
    backup = str(handler.mapper.serialize_document(), "UTF-8")
    change_reason = getattr(handler, "change_reason", None)
    db_objs = []
    for instance in instances:
        match (instance.__class__.__name__):
            case "DatasetMetadataRecord":
                model_key = "dataset"
            case "ServiceMetadataRecord":
                model_key = "service"
            case "ApplicationMetadataRecord":
                model_key = "application"
            case _:
                raise ValueError(
                    f"Unsupported model class {instance.__class__} for custom persistence.")

        values = _write_values_of(instance, handler, model_key)
        created = update = False
        db_obj = _record_of(instance.__class__, instance.file_identifier)

        if db_obj is None:
            # a new record gets the key of the parsed instance: the relations of
            # the document are set on the instance which carries that key
            db_obj = instance.__class__(
                file_identifier=instance.file_identifier, **values)
            try:
                # the savepoint keeps the transaction of the import usable when a
                # concurrent import of the same file identifier was faster: the
                # row it inserted is the one which answers from now on, which is
                # what get_or_create returned as well
                with transaction.atomic():
                    _save_record(db_obj, backup, change_reason)
                created = True
            except IntegrityError:
                if (db_obj := _record_of(instance.__class__, instance.file_identifier)) is None:
                    raise

        if db_obj is not None and not created and instance.date_stamp > db_obj.date_stamp:
            _apply_values(db_obj, values)
            _save_record(db_obj, backup, change_reason)
            update = True

        db_obj._custom_state = created, update
        db_objs.append(db_obj)

    final_key_map = handler.build_final_key_map(db_objs)
    original_key_map = handler.build_final_key_map(instances)
    handler.inject_private_attributes(final_key_map, original_key_map)

    return final_key_map
