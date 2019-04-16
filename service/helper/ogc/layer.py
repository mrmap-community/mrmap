#from PyQt5.Qt import left

class OGCLayer():
    def __init__(self, identifier=None, position=0, parent = None, left=1, right=None, title="", latlon_extent="(-90.0,-180.0,90.0,180.0)"):
        self.identifier = identifier
        self.position = position
        self.parent = parent
        self.lft = left
        self.rgt = right
        self.title = title # wms, wfs, wcs, ...
        self.latlon_extent = latlon_extent
        
    pass