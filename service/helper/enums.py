from enum import Enum


class ConnectionEnum(Enum):
    """ Defines all possible connection types

    """
    CURL = "curl"
    REQUESTS = "requests"
    URLLIB = "urllib"


class VersionEnum(Enum):
    """ Defines all supported versions

    """
    V_1_0_0 = "1.0.0"
    V_1_1_0 = "1.1.0"
    V_1_1_1 = "1.1.1"
    V_1_3_0 = "1.3.0"

    # wfs specific
    V_2_0_0 = "2.0.0"
    V_2_0_2 = "2.0.2"


class ServiceEnum(Enum):
    """ Defines all supported service types

    """

    WMS = "wms"
    WFS = "wfs"
    WMC = "wmc"
    DATASET = "dataset"


class ServiceOperationEnum(Enum):
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


class MetadataEnum(Enum):
    """ Defines all metadata types

    """

    DATASET = "dataset"
    SERVICE = "service"
    LAYER = "layer"
    FEATURETYPE = "featuretype"
