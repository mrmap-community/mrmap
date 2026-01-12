from typing import List

from registry.client.request.ogc_request import OGCRequest
from registry.client.utils import (get_requested_feature_types,
                                   get_requested_layers, get_requested_records)


class RequestedEntityResolver:

    @staticmethod
    def resolve(request: OGCRequest) -> List[str]:
        ctx = request.context

        if ctx.service == "wms":
            return get_requested_layers(request.ogc_query_params)

        if ctx.service == "wfs" and ctx.operation == "GetFeature":
            if ctx.method == "GET":
                return get_requested_feature_types(request.ogc_query_params)
            return request.xml_request.requested_feature_types

        if ctx.service == "csw" and ctx.operation == "GetRecordById":
            if ctx.method == "GET":
                return get_requested_records(request.ogc_query_params)
            return request.xml_request.ids

        return []
