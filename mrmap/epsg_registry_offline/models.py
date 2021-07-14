from django.contrib.gis.gdal import SpatialReference as GdalSpatialReference

from django.contrib.gis.gdal.prototypes.generation import (int_output)
from django.contrib.gis.gdal.libgdal import lgdal
from ctypes import c_void_p


# see c++ api ref: https://gdal.org/api/ogrspatialref.html
get_epsg_treats_as_lat_long = int_output(lgdal.OSREPSGTreatsAsLatLong, [c_void_p])
get_epsg_treats_as_northing_easting = int_output(lgdal.OSREPSGTreatsAsNorthingEasting, [c_void_p])


class Origin(enumerate):
    """Enum to declarative different origins"""
    CACHE = "from_cache"
    LOCAL_GDAL = "from_local_gdal"
    EPSG_REGISTRY = "from_remote_registry"


class SpatialReference(GdalSpatialReference):
    """Class to extend the :class:`django.contrib.gis.gdal.SpatialReference` class by additional attributes and
    properties.

    Implement the c gdal lib function calls for OSREPSGTreatsAsLatLong and OSREPSGTreatsAsNorthingEasting to get the
    axis order interpretation. See https://wiki.osgeo.org/wiki/Axis_Order_Confusion for detail problem.

    :param origin: the origin of this ``SpatialReference`` instance. Used in
                   :class:`epsg_registry_offline.registry.Registry` to signal where the information for this instance
                   comes from.
    :type origin: :class:`~Origin`
    """
    def __init__(self, origin: Origin = Origin.CACHE, *args, **kwargs):
        """Custom init function to store origin."""
        self.origin = origin
        super().__init__(*args, **kwargs)

    def __epsg_treats_as_lat_long(self):
        return bool(get_epsg_treats_as_lat_long(self.ptr))

    def __epsg_treats_as_northing_easting(self):
        return bool(get_epsg_treats_as_northing_easting(self.ptr))

    @property
    def is_yx_order(self) -> bool:
        """Return True if the axis order is lat,lon | north, east"""
        if self.geographic:
            return self.__epsg_treats_as_lat_long()
        elif self.projected:
            return self.__epsg_treats_as_northing_easting()

    @property
    def is_xy_order(self) -> bool:
        """Return True if the axis order is lon,lat | east, north"""
        return not self.is_yx_order
