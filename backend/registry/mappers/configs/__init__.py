from registry.mappers.configs.csw202 import XPATH_MAP as CSW202
from registry.mappers.configs.wfs200 import XPATH_MAP as WFS200
from registry.mappers.configs.wms111 import XPATH_MAP as WMS111
from registry.mappers.configs.wms130 import XPATH_MAP as WMS130

XPATH_MAP = WMS111 | WMS130 | WFS200 | CSW202
