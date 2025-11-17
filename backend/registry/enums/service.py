
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
    GET_MAP = 20, _("GetMap")
    GET_FEATURE_INFO = 21, _("GetFeatureInfo")


class SecureableWFSOperationEnum(SmartIntegerChoices):
    GET_FEATURE = 30, _("GetFeature")
    TRANSACTION = 31, _("Transaction")


class OGCOperationEnum(SmartIntegerChoices):
    """ Defines all known operation names"""
    # ALL
    GET_CAPABILITIES = 1, _("GetCapabilities")

    # WMS
    GET_MAP = 20, _("GetMap")
    GET_FEATURE_INFO = 21, _("GetFeatureInfo")
    DESCRIBE_LAYER = 22, _("DescribeLayer")
    GET_LEGEND_GRAPHIC = 23, _("GetLegendGraphic")
    GET_STYLES = 24, _("GetStyles")
    PUT_STYLES = 25, _("PutStyles")

    # WFS
    GET_FEATURE = 30, _("GetFeature")
    TRANSACTION = 31, _("Transaction")
    LOCK_FEATURE = 32, _("LockFeature")
    DESCRIBE_FEATURE_TYPE = 33, _("DescribeFeatureType")
    GET_FEATURE_WITH_LOCK = 34, _("GetFeatureWithLock")
    GET_GML_OBJECT = 35, _("GetGmlObject")
    LIST_STORED_QUERIES = 36, _("ListStoredQueries")
    GET_PROPERTY_VALUE = 37, _("GetPropertyValue")
    DESCRIBE_STORED_QUERIES = 38, _("DescribeStoredQueries")
    CREATE_STORED_QUERY = 39, _("CreateStoredQuery")
    DROP_STORED_QUERY = 40, _("DropStoredQuery")

    # CSW
    GET_RECORDS = 50, _("GetRecords")
    DESCRIBE_RECORD = 51, _("DescribeRecord")
    GET_RECORD_BY_ID = 52, _("GetRecordById")
    GET_DOMAIN = 53, _("GetDomain")
    GET_REPOSITORY_ITEM = 54, _("GetRepositoryItem")


class HttpMethodEnum(SmartIntegerChoices):
    """ Defines all important http method types

    """
    GET = 1, _("Get")
    POST = 2, _("Post")


class AuthTypeEnum(TextChoices):
    """ Defines all supported authentification types """
    BASIC = "http_basic"
    DIGEST = "http_digest"
