from MrMap.enums import EnumChoice


class OGCServiceVersionEnum(EnumChoice):
    """ Defines all supported versions

    """
    V_1_0_0 = "1.0.0"
    V_1_1_0 = "1.1.0"
    V_1_1_1 = "1.1.1"
    V_1_3_0 = "1.3.0"

    # wfs specific
    V_2_0_0 = "2.0.0"
    V_2_0_2 = "2.0.2"


class OGCServiceEnum(EnumChoice):
    """ Defines all supported service types

    """

    WMS = "wms"
    WFS = "wfs"
    WMC = "wmc"
    DATASET = "dataset"
    CSW = "csw"


class OGCOperationEnum(EnumChoice):
    """ Defines all known operation names

    """
    # ALL
    GET_CAPABILITIES = "GetCapabilities"

    # WMS
    GET_MAP = "GetMap"
    GET_FEATURE_INFO = "GetFeatureInfo"
    DESCRIBE_LAYER = "DescribeLayer"
    GET_LEGEND_GRAPHIC = "GetLegendGraphic"
    GET_STYLES = "GetStyles"
    PUT_STYLES = "PutStyles"

    # WFS
    GET_FEATURE = "GetFeature"
    TRANSACTION = "Transaction"
    LOCK_FEATURE = "LockFeature"
    DESCRIBE_FEATURE_TYPE = "DescribeFeatureType"
    GET_FEATURE_WITH_LOCK = "GetFeatureWithLock"
    GET_GML_OBJECT = "GetGmlObject"
    LIST_STORED_QUERIES = "ListStoredQueries"
    GET_PROPERTY_VALUE = "GetPropertyValue"
    DESCRIBE_STORED_QUERIES = "DescribeStoredQueries"

    # CSW
    GET_RECORDS = "GetRecords"
    DESCRIBE_RECORD = "DescribeRecord"
    GET_RECORD_BY_ID = "GetRecordById"


class HttpMethodEnum(EnumChoice):
    """ Defines all important http method types

    """
    GET = "Get"
    POST = "Post"


class AuthTypeEnum(EnumChoice):
    """ Defines all supported authentification types """
    BASIC = "http_basic"
    DIGEST = "http_digest"
    NONE = "none"
