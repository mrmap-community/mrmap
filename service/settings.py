"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 23.09.19

"""


# Metadata types
from service.helper.enums import ConnectionType, VersionTypes

MD_TYPE_FEATURETYPE = "featuretype"
MD_TYPE_DATASET = "dataset"
MD_TYPE_SERVICE = "service"
MD_TYPE_LAYER = "layer"

# Some special things
DEFAULT_CONNECTION_TYPE = ConnectionType.REQUESTS
DEFAULT_SERVICE_VERSION = VersionTypes.V_1_1_1

# semantic relation types
METADATA_RELATION_TYPE_VISUALIZES = "visualizes"
METADATA_RELATION_TYPE_DESCRIBED_BY = "describedBy"