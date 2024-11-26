"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from django.db.models.enums import TextChoices


class ReportType(TextChoices):
    """ Defines all possible content types for reports

    """
    HTML = 'text/html'
    JSON = 'application/json'


class RuleFieldNameEnum(TextChoices):
    """ Defines all possible field_name types

    """
    TITLE = "title"
    ABSTRACT = "abstract"
    ACCESS_CONSTRAINTS = "access_constraints"
    KEYWORDS = "keywords"
    FORMATS = "formats"
    REFERENCE_SYSTEM = "reference_system"


class RulePropertyEnum(TextChoices):
    """ Defines all possible property types

    """
    LEN = "len"
    COUNT = "count"


class RuleOperatorEnum(TextChoices):
    """ Defines all possible operator types

    """
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    NEQ = "!="


class ConformityTypeEnum(TextChoices):
    """ Defines all possible conformity types

    """
    INTERNAL = "internal"
    ETF = "etf"
