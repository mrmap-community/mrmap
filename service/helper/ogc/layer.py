#from PyQt5.Qt import left


class OGCLayer:
    def __init__(self, identifier=None, position=0, parent=None, type=None, name=None, title=None,
                 latlon_extent="(-90.0,-180.0,90.0,180.0)", queryable=False, opaque=False, cascaded=False, abstract=None):
        self.identifier = identifier
        self.position = position
        self.parent = parent
        self.service_type = type # wms, wfs, wcs, ...
        self.latlon_extent = latlon_extent
        self.is_queryable = queryable
        self.is_opaque = opaque
        self.is_cascaded = cascaded
        self.name = name
        self.title = title
        self.abstract = abstract
    pass
