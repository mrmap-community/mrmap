from django.db import models
from django.db.models import F, Q


class LayerMappingQuerySet(models.QuerySet):

    def unmatched_layers(self):
        return self.filter(old_layer__isnull=True)

    def auto_matched_but_unconfirmed(self):
        return self.filter(is_confirmed=False, old_layer__isnull=False)

    def is_autoupdate_able(self, service):
        qs = self.filter(old_layer__service=service)
        return not qs.filter(old_layer__isnull=True).exists()

    def with_changed_fields(self, *field_names: str):
        """Matched mappings where any selected scalar field differs."""
        if not field_names:
            return self.none()

        layer_model = self.model._meta.get_field("new_layer").related_model
        changed = Q()

        for name in field_names:
            # Accept direct scalar fields, including inherited fields.
            field = layer_model._meta.get_field(name)
            if not field.concrete or field.is_relation:
                raise ValueError(
                    f"{name!r} must be a concrete, non-relational Layer field"
                )

            old = f"old_layer__{field.name}"
            new = f"new_layer__{field.name}"

            old_null = Q(**{f"{old}__isnull": True})
            new_null = Q(**{f"{new}__isnull": True})

            changed |= (
                (old_null & ~new_null)
                | (~old_null & new_null)
                | (
                    ~old_null
                    & ~new_null
                    & ~Q(**{old: F(new)})
                )
            )

        return self.filter(old_layer__isnull=False).filter(changed)


class LayerMappingManager(models.Manager.from_queryset(LayerMappingQuerySet)):
    pass
