from django.core.files.base import ContentFile
from django.db.models.fields.generated import GeneratedField
from simple_history.models import HistoricalRecords


def get_or_create_metadatarecord(instances, handler):
    if hasattr(HistoricalRecords.context, "request") and hasattr(HistoricalRecords.context.request, "user"):
        current_user = HistoricalRecords.context.request.user
    else:
        current_user = None
    db_objs = []
    for instance in instances:
        handler.mapper
        defaults = {
            field.name: getattr(instance, field.name) for field in instance.__class__._meta.concrete_fields if field.name != "file_identifier" and not isinstance(field, GeneratedField)
        }
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

    final_key_map = handler.build_final_key_map(db_objs, ("file_identifier",))
    original_key_map = handler.build_final_key_map(
        instances, ("file_identifier",))
    handler.inject_private_attributes(final_key_map, original_key_map)

    return final_key_map
