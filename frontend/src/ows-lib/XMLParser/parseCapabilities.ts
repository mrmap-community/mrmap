
import { Polygon } from 'geojson'
import jsonpointer from 'jsonpointer'
import duration from 'moment'

import { ElevationDimension, Style, TempDimension, TimeDimension, WmsCapabilitites, WmsLayer } from './types'
import { getDocument } from './utils'

export const layerBboxToGeoJSON = (bbox: any): Polygon | undefined => {
    if (bbox === undefined) {
        return undefined
    }
    return {
        type: 'Polygon',
        coordinates: [
            [bbox["westBoundLongitude"], bbox["southBoundLatitude"]],
            [bbox["eastBoundLongitude"], bbox["southBoundLatitude"]],
            [bbox["eastBoundLongitude"], bbox["northBoundLatitude"]],
            [bbox["westBoundLongitude"], bbox["northBoundLatitude"]],
            [bbox["westBoundLongitude"], bbox["southBoundLatitude"]]
        ]
    }
}

export const parseTimeDimension = (timeDimension: any) => {

}

export const parseDimension = (dimension: any): TimeDimension | TempDimension | ElevationDimension | undefined => {
    const type = jsonpointer.get(dimension, '/@_name')
    const units = jsonpointer.get(dimension, '/@_units')
    if (type === 'time' && units === 'ISO8601') {
        // TimeDimension handling
        const dimensionValue = jsonpointer.get(dimension, '/#text')
        const [start, stop, resolution] = dimensionValue.split('/')

        return {
            start: new Date(start),
            stop: new Date(stop) ?? undefined,
            resolution: duration(resolution) ?? undefined
        }

    } else if (type === 'temperature') {
        // Temperature dimension handling
        return {
            unit: jsonpointer.get(dimension, '/units'),
            unitSymbol: jsonpointer.get(dimension, '/unitSymbol'),
            default: jsonpointer.get(dimension, '/default'),
            values: jsonpointer.get(dimension, '/#text').split('/')
        }
    } else if (type === 'elevation') {
        // Elevation dimension handling
        return {
            crs: jsonpointer.get(dimension, '/units'),
            unitSymbol: jsonpointer.get(dimension, '/unitSymbol'),
            default: jsonpointer.get(dimension, '/default'),
            values: jsonpointer.get(dimension, '/#text').split('/')
        }
    }
}

export const parseStyle = (style: any): Style => {
    return {
        metadata: {
            name: jsonpointer.get(style, '/Name'),
            title: jsonpointer.get(style, '/Title'),
            abstract: jsonpointer.get(style, '/Abstract')
        },
        legendUrl: {
            mimeType: jsonpointer.get(style, '/LegendURL/Format'),
            href: jsonpointer.get(style, '/LegendURL/OnlineResource/@_href'),
            width: jsonpointer.get(style, '/LegendURL/@_width'),
            height: jsonpointer.get(style, '/LegendURL/@_height')
        }
    }
}

export const forceArray = (obj: any): Array<any> => {
    return Array.isArray(obj) ? obj : [obj]
}

export const parseLayer = (layer: any): WmsLayer => {
    const abstract = jsonpointer.get(layer, '/Abstract')
    const parsedCrsV1 = jsonpointer.get(layer, '/SRS')
    const parsedCrsV3 = jsonpointer.get(layer, '/CRS')
    const crs = parsedCrsV1 === undefined ? forceArray(parsedCrsV3 ?? []) : forceArray(parsedCrsV1 ?? [])

    const parsedStyles: any = jsonpointer.get(layer, '/Style')
    const styles = parsedStyles === undefined ? [] : forceArray(parsedStyles).map((style: any) => parseStyle(style))

    const minScaleDenominator = jsonpointer.get(layer, '/MinScaleDenomnator')
    const maxScaleDenominator = jsonpointer.get(layer, '/MaxScaleDenomnator')

    const isQueryable = jsonpointer.get(layer, '/@_queryable')
    const isOpaque = jsonpointer.get(layer, '/@_opaque')
    const isCascaded = jsonpointer.get(layer, '/@_cascaded')

    const layerObj: WmsLayer = {
        metadata: {
            title: jsonpointer.get(layer, '/Title'),
            name: jsonpointer.get(layer, '/Name'),
            ...(abstract && { abstract: abstract })
        },
        ...(crs?.length > 0 && { referenceSystems: crs }),
        bbox: layerBboxToGeoJSON(jsonpointer.get(layer, '/EX_GeographicBoundingBox')),
        ...(styles?.length > 0 && { styles: styles }),
        ...(minScaleDenominator && { minScaleDenominator: Number.parseFloat(minScaleDenominator) }),
        ...(maxScaleDenominator && { maxScaleDenominator: Number.parseFloat(maxScaleDenominator) }),
        ...(isQueryable && { isQueryable: Boolean(Number(isQueryable)) }),
        ...(isOpaque && { isOpaque: Boolean(Number(isOpaque)) }),
        ...(isCascaded && { isCascaded: Boolean(Number(isCascaded)) })
    }

    const sublayer = jsonpointer.get(layer, '/Layer')

    if (sublayer === undefined) {
        // no sublayers
    } else if (Array.isArray(sublayer)) {
        // ancestor node ==> children are there
        const parsedSublayers: WmsLayer[] = []
        sublayer.forEach((sublayer) => {
            const parsedLayer = parseLayer(sublayer)
            if (parsedLayer !== undefined) {
                parsedSublayers.push(parsedLayer)
            }
        })
        layerObj.children = parsedSublayers
    } else {
        // leaf node
        const parsedLayer = parseLayer(sublayer)
        if (parsedLayer !== undefined) {
            layerObj.children = [parsedLayer]
        }
    }

    return layerObj
}

export const parseWms = (xml: string): WmsCapabilitites => {

    const parsedCapabilites = getDocument(xml)

    let rootNodeName = "WMS_Capabilities"

    if ("WMT_MS_Capabilities" in parsedCapabilites) {
        rootNodeName = "WMT_MS_Capabilities"
    }
    // TODO: implement parser for version 1.1.1 differs to 1.3.0
    const capabilities = {
        version: jsonpointer.get(parsedCapabilites, `/${rootNodeName}/@_version`),
        metadata: {
            name: jsonpointer.get(parsedCapabilites, `/${rootNodeName}/Service/Name`),
            title: jsonpointer.get(parsedCapabilites, `/${rootNodeName}/Service/Title`),
            abstract: jsonpointer.get(parsedCapabilites, `/${rootNodeName}/Service/Abstract`),
        },
        operationUrls: {
            getCapabilities: {
                mimeTypes: jsonpointer.get(parsedCapabilites, `/${rootNodeName}/Capability/Request/GetCapabilities/Format`),
                get: jsonpointer.get(parsedCapabilites, `/${rootNodeName}/Capability/Request/GetCapabilities/DCPType/HTTP/Get/OnlineResource/@_href`),
                post: jsonpointer.get(parsedCapabilites, `/${rootNodeName}/Capability/Request/GetCapabilities/DCPType/HTTP/Post/OnlineResource/@_href`)
            },
            getMap: {
                mimeTypes: jsonpointer.get(parsedCapabilites, `/${rootNodeName}/Capability/Request/GetMap/Format`),
                get: jsonpointer.get(parsedCapabilites, `/${rootNodeName}/Capability/Request/GetMap/DCPType/HTTP/Get/OnlineResource/@_href`),
                post: jsonpointer.get(parsedCapabilites, `/${rootNodeName}/Capability/Request/GetMap/DCPType/HTTP/Post/OnlineResource/@_href`)
            },
            getFeatureInfo: {
                mimeTypes: jsonpointer.get(parsedCapabilites, `/${rootNodeName}/Capability/Request/GetFeatureInfo/Format`),
                get: jsonpointer.get(parsedCapabilites, `/${rootNodeName}/Capability/Request/GetFeatureInfo/DCPType/HTTP/Get/OnlineResource/@_href`),
                post: jsonpointer.get(parsedCapabilites, `/${rootNodeName}/Capability/Request/GetFeatureInfo/DCPType/HTTP/Post/OnlineResource/@_href`)
            }
        },
        rootLayer: parseLayer(jsonpointer.get(parsedCapabilites, `/${rootNodeName}/Capability/Layer`))
    }

    return capabilities
}