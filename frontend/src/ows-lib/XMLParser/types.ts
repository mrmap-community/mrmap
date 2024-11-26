import { Polygon } from 'geojson'
import { Duration } from 'moment'


export interface Metadata {
    title: string
    name: string
    abstract?: string
}

export interface Dimension {

}

export interface TempDimension {
    unit: string
    unitSymbol: string
    default: number
    values: number[]
}

export interface ElevationDimension {
    crs: string
    unitSymbol: string
    default: string
    values: number[]
}

export interface TimeDimension {
    start: Date
    stop?: Date
    default?: Date
    resolution?: Duration
}



export interface LegendUrl {
    href: URL
    mimeType: string
    width: number
    height: number
}

export interface Style {
    metadata: Metadata
    legendUrl?: LegendUrl
}

export interface WmsLayer {
    metadata: Metadata
    referenceSystems?: string[]
    bbox?: Polygon[]
    dimension?: (TimeDimension | TempDimension | ElevationDimension)[]
    children?: WmsLayer[]
    parent?: WmsLayer
    path?: WmsLayer[]
    styles?: Style[]
    minScaleDenominator?: number
    maxScaleDenominator?: number
    isQueryable?: boolean
    isQpaque?: boolean
    isCascaded?: boolean
}

export interface InheritableProperties {
    referenceSystems: string[]          // 1+; add
    styles: Style[]                     // 0+; add
    bbox: Polygon[]                     // 1+; replace
    dimension?: (TimeDimension | TempDimension | ElevationDimension)[] // 0+; replace
    minScaleDenominator?: number        // 0/1; replace
    maxScaleDenominator?: number        // 0/1; replace
    isQueryable?: boolean               // replace
    isQpaque?: boolean                  // replace
    isCascaded?: boolean                // replace
}

export interface OperationUrl {
    mimeTypes: string[]
    get: string
    post?: string
}

export interface Capabilites {
    version: string
    metadata: Metadata
    operationUrls: {
        getCapabilities: OperationUrl
    }
}

export interface WmsCapabilitites extends Capabilites {
    rootLayer: WmsLayer
    operationUrls: {
        getCapabilities: OperationUrl
        getMap: OperationUrl
        getFeatureInfo?: OperationUrl // this shall be optional operation
    }
}

export interface WfsCapabilitites extends Capabilites {
    // TODO: featuretypes
    operationUrls: {
        getCapabilities: OperationUrl
        // TODO: other operation urls
    }
}