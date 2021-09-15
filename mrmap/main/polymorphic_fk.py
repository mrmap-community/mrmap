from django.core.exceptions import ValidationError


class PolymorphicForeignKey:
    """
    Provide a polymorphic many-to-one relation through a number of ``ForeignKey`` fields.
    """

    def __init__(self, *fk_fields):
        self.fk_fields = fk_fields

    def get_target(self, obj):
        """
        Return the target object.
        """
        for fk_field in self.fk_fields:
            # check for existing id first (avoid DoesNotExist exceptions)
            fk = getattr(obj, fk_field + "_id")
            if fk:
                return getattr(obj, fk_field)

    def get_target_field(self, obj):
        """
        Return the name of the used target field (if one is not None).
        """
        for fk_field in self.fk_fields:
            # check for existing id first (avoid DoesNotExist exceptions)
            fk = getattr(obj, fk_field + "_id")
            if fk:
                return fk_field

    def set_target(self, obj, value):
        # TODO handle None -> set all fk_fields
        for fk_field_name in self.fk_fields:
            fk_field = obj._meta.get_field(fk_field_name)
            if isinstance(value, fk_field.related_model):
                setattr(obj, fk_field_name, value)
                break

    def validate(self, obj):
        """
        Raise ValidationError if the polymorphic fk constraint (exactly one fk must be not empty) is violated.
        """
        non_empty_fields = [fk_field for fk_field in self.fk_fields if (getattr(obj, fk_field + "_id"))]
        if not non_empty_fields:
            raise ValidationError(f"PolymorphicForeignKey violation: One of the fields {self.fk_fields} must be set.")
        if len(non_empty_fields) > 1:
            raise ValidationError(f"PolymorphicForeignKey violation: More than field ({non_empty_fields}) is set.")
