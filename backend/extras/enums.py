from django.db.models.enums import ChoicesMeta, IntegerChoices


class SmartIntegerChoicesMeta(ChoicesMeta):
    """Erweitert Django’s IntegerChoices-Meta, um Label-Lookup zu erlauben."""

    def __call__(cls, value, *args, **kwargs):
        # Wenn int → normales Verhalten
        if isinstance(value, int):
            return super().__call__(value, *args, **kwargs)

        # Wenn string → Label-basiertes Matching
        if isinstance(value, str):
            normalized = value.lower().replace("_", "").strip()
            for member in cls:
                member_label = str(member.label).lower().replace("_", "")
                if member_label == normalized:
                    return member
            return None  # kein Match → None statt Exception

        return None


class SmartIntegerChoices(IntegerChoices, metaclass=SmartIntegerChoicesMeta):
    """IntegerChoices mit intelligentem Label-Lookup."""
    pass
