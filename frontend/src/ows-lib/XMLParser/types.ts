import { Duration } from 'moment';


export interface Metadata {
    title: string
    name: string
    abstract?: string
}

export type Dimension = Record<string, unknown>;

/** A dimension exactly as the capabilities advertise it: the stated name, units, default and the raw value text. */
export interface AdvertisedDimension {
    name: string
    values: string
    units?: string
    unitSymbol?: string
    default?: string
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
    bbox?: [number, number, number, number]
    bboxBounds?: [number, number, number, number]
    dimension?: (TimeDimension | TempDimension | ElevationDimension)[]
    advertisedDimension?: AdvertisedDimension[]
    children?: WmsLayer[]
    parent?: WmsLayer
    path?: WmsLayer[]
    styles?: Style[]
    minScaleDenominator?: number
    maxScaleDenominator?: number
    isQueryable?: boolean
    isOpaque?: boolean
    isCascaded?: boolean
}

/**
 * The settings a WMS layer inherits from its parent layers (WMS 1.3.0 section 7.2.4.1.1, WMS 1.1.1
 * section 4.6.4.1). Reference systems and styles are inherited and added to, every other setting is
 * replaced by the innermost layer which states it - including a stated "0" or false value, which
 * overrides an inherited true value instead of counting as "not stated".
 */
export interface InheritableProperties {
    referenceSystems: string[]          // 1+; add
    styles: Style[]                     // 0+; add
    bbox?: WmsLayer["bbox"]             // 1+; replace
    dimension?: (TimeDimension | TempDimension | ElevationDimension)[] // 0+; replace
    advertisedDimension?: AdvertisedDimension[] // 0+; replace by name
    minScaleDenominator?: number        // 0/1; replace
    maxScaleDenominator?: number        // 0/1; replace
    isQueryable?: boolean               // replace
    isOpaque?: boolean                  // replace
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