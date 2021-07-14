from django.core.cache import cache
from requests import Request, Session
from epsg_registry_offline.models import SpatialReference, Origin


class Registry(object):
    """Cached Epsg Registry based on django cache framework.

    Cause reference systems from the epsg namespace are dynamic (see [CIT_EPSG]_) we need to fetch them from the remote
    EPSG API (https://apps.epsg.org/api/swagger/ui/index).

    .. [CIT_EPSG] The EPSG Registry has migrated from a previous platform. The data model on this new site has been
       upgraded to follow the ISO 19111:2019 revisions for dynamic datums, geoid-based vertical datums, datum ensembles
       and derived projected coordinate reference systems. (from https://epsg.org/home.html)

    To get the :class:`epsg_registry_offline.models.SpatialReference` objects the workflow described in
    :meth:`epsg_registry_offline.registry.Registry.get`` is used.

    **Example usage:**

    .. code-block:: python
       from epsg_registry_offline import Registry

       registry = Registry()
       sr = registry.get(srid=4326)

       print(sr.is_xy_order())
       >>> True
    """

    epsg_api_url = "https://apps.epsg.org/api/v1/"
    cache_prefix = "epsg_registry_offline"
    ttl = 7

    def __init__(self, proxies=None):
        self.proxies = proxies

    def coord_ref_system_export(self, srid: int):
        """Fetch the wkt for a given srid from remote epsg api

        :return: the spatial reference
        :rtype: :class:`epsg_registry_offline.models.SpatialReference`
        """
        try:
            request = Request(method="GET", url=f"{self.epsg_api_url}CoordRefSystem/{srid}/export/?format=wkt")
            s = Session()
            if self.proxies:
                s.proxies = self.proxies
            response = s.send(request=request.prepare())
            if response.status_code < 300:
                return SpatialReference(origin=Origin.EPSG_REGISTRY, srs_input=response.content, srs_type="wkt")
        except ConnectionError:
            pass
        return None

    def get(self, srid: int):
        """Return the SpatialReference object by given srid from three different origins.
        1th: cache is uses to lookup a cached spatial reference
        2th: remote epsg api is fetched to lookup the remote spatial reference
        3th: fallback to the local gdal registry

        :return: the initialized spatial reference object with the origin information.
        :rtype: :class:`epsg_registry_offline.models.SpatialReference`

        """
        cached_crs = cache.get(key=f"{self.cache_prefix}-{srid}")
        if not cached_crs:
            crs = self.coord_ref_system_export(srid=srid)
            if crs:
                self.set(srid=srid, crs=crs)
            else:
                crs = SpatialReference(origin=Origin.LOCAL_GDAL, srs_input=srid)
            return crs
        else:
            return SpatialReference(srs_input=cached_crs, srs_type="wkt")

    def set(self, srid: int, crs: SpatialReference):
        """Store the wkt of the given crs"""
        cache.set(key=f"{self.cache_prefix}-{srid}", value=crs.wkt)
