from django.db.models.enums import TextChoices

from extras.enums import SmartIntegerChoices


class OGCServiceVersionEnum(SmartIntegerChoices):
    """ Defines all supported versions

    """
    V_1_0_0 = 1, "1.0.0"
    V_1_1_0 = 11, "1.1.0"
    V_1_1_1 = 111, "1.1.1"
    V_1_3_0 = 130, "1.3.0"

    # wfs specific
    V_2_0_0 = 200, "2.0.0"
    V_2_0_2 = 202, "2.0.2"


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
    GET_MAP = 20, "GetMap"
    GET_FEATURE_INFO = 21, "GetFeatureInfo"


class SecureableWFSOperationEnum(SmartIntegerChoices):
    GET_FEATURE = 30, "GetFeature"
    TRANSACTION = 31, "Transaction"


class OGCOperationEnum(SmartIntegerChoices):
    """ Defines all known operation names"""
    # ALL
    GET_CAPABILITIES = 1, "GetCapabilities"

    # WMS
    GET_MAP = 20, "GetMap"
    GET_FEATURE_INFO = 21, "GetFeatureInfo"
    DESCRIBE_LAYER = 22, "DescribeLayer"
    GET_LEGEND_GRAPHIC = 23, "GetLegendGraphic"
    GET_STYLES = 24, "GetStyles"
    PUT_STYLES = 25, "PutStyles"

    # WFS
    GET_FEATURE = 30, "GetFeature"
    TRANSACTION = 31, "Transaction"
    LOCK_FEATURE = 32, "LockFeature"
    DESCRIBE_FEATURE_TYPE = 33, "DescribeFeatureType"
    GET_FEATURE_WITH_LOCK = 34, "GetFeatureWithLock"
    GET_GML_OBJECT = 35, "GetGmlObject"
    LIST_STORED_QUERIES = 36, "ListStoredQueries"
    GET_PROPERTY_VALUE = 37, "GetPropertyValue"
    DESCRIBE_STORED_QUERIES = 38, "DescribeStoredQueries"
    CREATE_STORED_QUERY = 39, "CreateStoredQuery"
    DROP_STORED_QUERY = 40, "DropStoredQuery"

    # CSW
    GET_RECORDS = 50, "GetRecords"
    DESCRIBE_RECORD = 51, "DescribeRecord"
    GET_RECORD_BY_ID = 52, "GetRecordById"
    GET_DOMAIN = 53, "GetDomain"
    GET_REPOSITORY_ITEM = 54, "GetRepositoryItem"
    HARVEST = 55, "Harvest"


class HttpMethodEnum(SmartIntegerChoices):
    """ Defines all important http method types"""
    GET = 1, "Get"
    POST = 2, "Post"


class AuthTypeEnum(TextChoices):
    """ Defines all supported authentification types """
    BASIC = "http_basic"
    DIGEST = "http_digest"
