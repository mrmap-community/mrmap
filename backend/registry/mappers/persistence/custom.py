from django.core.files.base import ContentFile
from django.db.models import ForeignKey
from django.db.models.fields.generated import GeneratedField
from simple_history.models import HistoricalRecords


def _defaults_of_instance(instance):
    """The field values of a parsed instance, to create or update the db record
    with.

    A foreign key is read by its key column. The relation descriptor of an
    instance which was only parsed means a query for the related record and
    raises RelatedObjectDoesNotExist if the mapper did not set the key at all,
    which hides the field that is really missing.
    """
    defaults = {}
    for field in instance.__class__._meta.concrete_fields:
        if field.name == "file_identifier" or isinstance(field, GeneratedField):
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


def get_or_create_metadatarecord(instances, handler):
    if hasattr(HistoricalRecords.context, "request") and hasattr(HistoricalRecords.context.request, "user"):
        current_user = HistoricalRecords.context.request.user
    else:
        current_user = None
    db_objs = []
    for instance in instances:
        handler.mapper
        defaults = _defaults_of_instance(instance)

        match (instance.__class__.__name__):
            case "DatasetMetadataRecord":
                key = "dataset"
            case "ServiceMetadataRecord":
                key = "service"
            case _:
                raise ValueError(
                    f"Unsupported model class {instance.__class__} for custom persistence.")

        passed_defaults = handler.defaults.get(key, {})
        for key, value in passed_defaults.items():
            defaults.setdefault(key, value)

        update = False
        db_obj, created = instance.__class__.objects.select_for_update().get_or_create(
            defaults=defaults, file_identifier=instance.file_identifier)

        db_objs.append(db_obj)

        if not created and instance.date_stamp > db_obj.date_stamp:
            # run update on fields
            for key, value in defaults.items():
                if key == db_obj._meta.pk.name:
                    # the primary key of the parsed but unsaved instance is a
                    # fresh uuid which no row carries: copying it would move
                    # the fetched row away instead of updating it (#811)
                    continue
                setattr(db_obj, key, value)
            db_obj.last_modified_by = current_user
            db_obj.save()
            update = True

        db_obj._custom_state = created, update
        if created or update:
            # TODO: on update we need to check custom metadata
            # TODO: delete old file
            db_obj.xml_backup_file.save(name='md_metadata.xml',
                                        content=ContentFile(str(handler.mapper.serialize_document(), "UTF-8")))

    final_key_map = handler.build_final_key_map(db_objs)
    original_key_map = handler.build_final_key_map(instances)
    handler.inject_private_attributes(final_key_map, original_key_map)

    return final_key_map
