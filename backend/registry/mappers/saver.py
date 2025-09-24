from django.db import transaction
from django.db.models import ForeignKey, ManyToManyField, OneToOneField


class CapabilitySaver:
    def __init__(self):
        self.saved = {}

    @transaction.atomic
    def save_instance(self, instance, spec):
        model_cls = type(instance)
        create_mode = spec.get("_create_mode", "plain")

        # Normales Save oder get_or_create
        if create_mode == "get_or_create":
            lookup_fields = {
                f.name: getattr(instance, f.name)
                for f in model_cls._meta.fields
                if f.name != "id"
            }
            instance, _ = model_cls.objects.get_or_create(**lookup_fields)
        else:
            instance.save()

        # Child-Felder speichern
        for field_name, field_spec in spec.get("fields", {}).items():
            parsed_attr = getattr(instance, f"_{field_name}_parsed", None)
            if not parsed_attr:
                continue

            field_obj = model_cls._meta.get_field(field_name)

            if isinstance(field_obj, ManyToManyField) or field_spec.get("_many"):
                # Liste von Objekten speichern und zuweisen
                objs = []
                for child in parsed_attr:
                    saved_child = self.save_instance(child, field_spec)
                    objs.append(saved_child)
                getattr(instance, field_name).set(objs)

            elif isinstance(field_obj, (ForeignKey, OneToOneField)):
                saved_child = self.save_instance(parsed_attr, field_spec)
                setattr(instance, field_name, saved_child)
                instance.save(update_fields=[field_name])

        return instance

    def save(self, parsed, spec):
        if isinstance(parsed, list):
            return [self.save_instance(inst, spec) for inst in parsed]
        else:
            return self.save_instance(parsed, spec)
