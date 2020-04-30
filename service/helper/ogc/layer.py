
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
        self.get_capabilities_uri_GET = None
        self.get_capabilities_uri_POST = None
        self.get_map_uri_GET = None
        self.get_map_uri_POST = None
        self.get_feature_info_uri_GET = None
        self.get_feature_info_uri_POST = None
        self.describe_layer_uri_GET = None
        self.describe_layer_uri_POST = None
        self.get_legend_graphic_uri_GET = None
        self.get_legend_graphic_uri_POST = None
        self.get_styles_uri_GET = None
        self.get_styles_uri_POST = None
        self.dimension_list = []
        self.style = None
        self.child_layers = []

        self.iso_metadata = []
