from typing import List

from django.contrib.gis.geos import Polygon
from ows_lib.xml_mapper.capabilities.mixins import (OGCServiceMixin,
                                                    ReferenceSystemMixin)


class FeatureTypeMixin:
    def __str__(self):
        return self.identifier

    @property
    def _bbox_lower_corner(self):
        raise NotImplementedError

    @property
    def _bbox_upper_corner(self):
        raise NotImplementedError

    @property
    def _default_crs_class(self):
        return NotImplementedError

    @property
    def _other_crs_class(self):
        return NotImplementedError

    @property
    def bbox_lat_lon(self) -> Polygon:
        # there is no default xmlmap field which parses to a geos polygon. So we convert it here.

        if self._bbox_lower_corner and self._bbox_upper_corner:
            min_x = float(self._bbox_lower_corner.split(" ")[0])
            min_y = float(self._bbox_lower_corner.split(" ")[1])
            max_x = float(self._bbox_upper_corner.split(" ")[0])
            max_y = float(self._bbox_upper_corner.split(" ")[1])

            return Polygon(
                ((min_x, min_y),
                 (min_x, max_y),
                 (max_x, max_y),
                 (max_x, min_y),
                 (min_x, min_y))
            )

    @bbox_lat_lon.setter
    def bbox_lat_lon(self, polygon: Polygon) -> None:
        # Custom setter function to mapp the geos Polygon object back to the xml attributes
        self._bbox_lower_corner = f"{polygon.extent[0]} {polygon.extent[1]}"
        self._bbox_upper_corner = f"{polygon.extent[2]} {polygon.extent[3]}"

    @property
    def reference_systems(self) -> List[ReferenceSystemMixin]:
        if self._default_reference_system and self._other_reference_systems:
            return [self._default_reference_system].extend(self._other_reference_systems)
        elif self._default_reference_system:
            return [self._default_reference_system]
        else:
            return []

    @reference_systems.setter
    def reference_systems(self, value: List[ReferenceSystemMixin]):
        """custom setter function to pass the first given reference system as default reference system"""
        first = True
        for crs in value:
            if first:
                self._default_reference_system = self._default_crs_class(
                    context={"_ref_system": crs.__str__()})
                first = False
            else:
                self._other_reference_systems = self._other_crs_class(
                    context={"_ref_system": crs.__str__()})


class WebFeatureServiceMixin(OGCServiceMixin):
    """Abstract class for WebMapService xml mappers,
    which implements functionality for global usage."""

    _possible_operations = ["GetCapabilities", "DescribeFeatureType",
                            "GetFeature", "GetPropertyValue", "ListStoredQueries", "DescribeStoredQueries", "CreateStoredQuery", "DropStoredQuery"]

    def get_feature_type_by_identifier(self, identifier: str):
        return next((feature_type for feature_type in self.feature_types if feature_type.identifier == identifier), None)
