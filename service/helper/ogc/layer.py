#from PyQt5.Qt import left


class OGCLayer:
    def __init__(self, identifier=None, position=0, parent=None, title=None, queryable=False, opaque=False,
                 cascaded=False, abstract=None):
        self.identifier = identifier
        self.position = position
        self.parent = parent
        self.is_queryable = queryable
        self.is_opaque = opaque
        self.is_cascaded = cascaded
        self.title = title
        self.abstract = abstract

        # capabilities
        self.capability_keywords = []
        self.capability_online_resource = None
        self.capability_projection_system = []
        self.capability_scale_hint = {
            "min": 0,
            "max": 0,
        }
        self.capability_bbox_lat_lon = {
            "minx": 0,
            "miny": 0,
            "maxx": 0,
            "maxy": 0,
        }
        self.capability_bbox_srs = {}

        self.format_list = []
        self.get_capabilities_uri = None
        self.get_map_uri = None
        self.get_feature_info_uri = None
        self.describe_layer_uri = None
        self.get_legend_graphic_uri = None
        self.get_styles_uri = None
        self.dimension = []
        self.style = {}
        self.child_layer = []

        self.iso_metadata = None
