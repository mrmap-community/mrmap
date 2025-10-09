
from django.db.models.enums import TextChoices
from django.utils.translation import gettext_lazy as _
from extras.enums import SmartIntegerChoices


class OGCServiceVersionEnum(SmartIntegerChoices):
    """ Defines all supported versions

    """
    V_1_0_0 = 1, _("1.0.0")
    V_1_1_0 = 11, _("1.1.0")
    V_1_1_1 = 111, _("1.1.1")
    V_1_3_0 = 130, _("1.3.0")

    # wfs specific
    V_2_0_0 = 200, _("2.0.0")
    V_2_0_2 = 202, _("2.0.2")


class OGCServiceEnum(TextChoices):
    """ Defines all supported service types

    """
    ALL = "all"
    WMS = "wms"
    WFS = "wfs"
    WMC = "wmc"
    DATASET = "dataset"
    CSW = "csw"


class SecureableWMSOperationEnum(SmartIntegerChoices):
    GET_MAP = 2, _("GetMap")
    GET_FEATURE_INFO = 3, _("GetFeatureInfo")


class SecureableWFSOperationEnum(SmartIntegerChoices):
    GET_FEATURE = 8, _("GetFeature")
    TRANSACTION = 9, _("Transaction")


class OGCOperationEnum(SmartIntegerChoices):
    """ Defines all known operation names"""
    # ALL
    GET_CAPABILITIES = 1, _("GetCapabilities")

    # WMS
    GET_MAP = 2, _("GetMap")
    GET_FEATURE_INFO = 3, _("GetFeatureInfo")
    DESCRIBE_LAYER = 4, _("DescribeLayer")
    GET_LEGEND_GRAPHIC = 5, _("GetLegendGraphic")
    GET_STYLES = 6, _("GetStyles")
    PUT_STYLES = 7, _("PutStyles")

    # WFS
    GET_FEATURE = 8, _("GetFeature")
    TRANSACTION = 9, _("Transaction")
    LOCK_FEATURE = 10, _("LockFeature")
    DESCRIBE_FEATURE_TYPE = 11, _("DescribeFeatureType")
    GET_FEATURE_WITH_LOCK = 12, _("GetFeatureWithLock")
    GET_GML_OBJECT = 13, _("GetGmlObject")
    LIST_STORED_QUERIES = 14, _("ListStoredQueries")
    GET_PROPERTY_VALUE = 15, _("GetPropertyValue")
    DESCRIBE_STORED_QUERIES = 16, _("DescribeStoredQueries")

    # CSW
    GET_RECORDS = 17, _("GetRecords")
    DESCRIBE_RECORD = 18, _("DescribeRecord")
    GET_RECORD_BY_ID = 19, _("GetRecordById")


class HttpMethodEnum(SmartIntegerChoices):
    """ Defines all important http method types

    """
    GET = 1, _("Get")
    POST = 2, _("Post")


class AuthTypeEnum(TextChoices):
    """ Defines all supported authentification types """
    BASIC = "http_basic"
    DIGEST = "http_digest"
