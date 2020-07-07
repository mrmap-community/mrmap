from enum import Enum


class EnumChoice(Enum):
    """ Provides basic functionality for Enums

    """
    @classmethod
    def as_choices(cls):
        choices = [(None, "---")] + [(enum.value, enum.name) for enum in cls]
        return choices


class ConnectionEnum(EnumChoice):
    """ Defines all possible connection types

    """
    CURL = "curl"
    REQUESTS = "requests"
    URLLIB = "urllib"


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


class MetadataEnum(EnumChoice):
    """ Defines all metadata types

    """
    DATASET = "dataset"
    SERVICE = "service"
    LAYER = "layer"
    FEATURETYPE = "featuretype"


class DocumentEnum(EnumChoice):
    """ Defines all document types

    """
    CAPABILITY = "Capability"
    METADATA = "Metadata"


class ResourceOriginEnum(EnumChoice):
    """ Defines origins from where a resource could be coming from

    """
    CAPABILITIES = "Capabilities"
    UPLOAD = "Upload"
    EDITOR = "Editor"


class CategorySourceEnum(EnumChoice):
    """ Defines sources for categories

    """
    ISO = "iso"
    INSPIRE = "inspire"

    @classmethod
    def all_values_as_list(cls):
        return [enum.value for enum in cls]

    @classmethod
    def all_names_as_list(cls):
        return [enum.name for enum in cls]
