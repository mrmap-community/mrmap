"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG
Contact: suleiman@terrestris.de
Created on: 27.10.20

"""
from MrMap.enums import EnumChoice

class ReportType(EnumChoice):
    """ Defines all possible content types for reports

    """
    HTML = 'text/html'
    JSON = 'application/json'

class RuleFieldNameEnum(EnumChoice):
    """ Defines all possible field_name types

    """
    TITLE = "title"
    ABSTRACT = "abstract"
    ACCESS_CONSTRAINTS = "access_constraints"
    KEYWORDS = "keywords"
    FORMATS = "formats"
    REFERENCE_SYSTEM = "reference_system"


class RulePropertyEnum(EnumChoice):
    """ Defines all possible property types

    """
    LEN = "len"
    COUNT = "count"


class RuleOperatorEnum(EnumChoice):
    """ Defines all possible operator types

    """
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="
    NEQ = "!="


class ConformityTypeEnum(EnumChoice):
    """ Defines all possible conformity types

    """
    INTERNAL = "internal"
    ETF = "etf"
