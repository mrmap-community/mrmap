from enum import Enum


class ConnectionType(Enum):
    """ Defines all possible connection types

    """
    CURL = "curl"
    REQUESTS = "requests"
    URLLIB = "urllib"


class VersionTypes(Enum):
    """ Defines all supported versions

    """
    V_1_0_0 = "1.0.0"
    V_1_1_0 = "1.1.0"
    V_1_1_1 = "1.1.1"
    V_1_3_0 = "1.3.0"


class ServiceTypes(Enum):
    """ Defines all supported service types

    """

    WMS = "wms"
    WFS = "wfs"
    WMC = "wmc"
    DATASET = "dataset"
