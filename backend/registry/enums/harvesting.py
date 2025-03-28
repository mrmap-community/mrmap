from django.db.models.enums import TextChoices


class ErrorType(TextChoices):
    """ Defines all possible content types for reports

    """
    REQUEST = 'request'
    PARSING = 'parsing'


class CollectingStatenEnum(TextChoices):
    """ Defines sources for categories
    """
    NEW = "new"
    UPDATED = "updated"
    EXISTING = "existing"
    DUPLICATED = "duplicated"
