from django.db.models.enums import TextChoices


class ErrorType(TextChoices):
    """ Defines all possible content types for reports

    """
    REQUEST = 'request'
    PARSING = 'parsing'
