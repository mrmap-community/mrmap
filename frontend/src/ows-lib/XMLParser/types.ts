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

/**
 * One `ows:Operation` entry of a WFS 2.0 OperationsMetadata section. The
 * advertised `ows:Parameter` AllowedValues and `ows:Constraint` values are
 * retained with their exact spellings, because WFS requests must send the
 * tokens the service declared. A missing entry stays missing: it must never
 * be read as "unbounded" or "supported".
 */
export interface WfsOperation extends OperationUrl {
    /** AllowedValues of every ows:Parameter of the operation, keyed by name. */
    parameters: Record<string, string[]>
    /**
     * ows:Constraint values of the operation: the DefaultValue when stated,
     * otherwise the single AllowedValues entry. Constraints without an
     * answerable value (NoValues without DefaultValue) are omitted, so an
     * absent key means "not advertised" and not "unlimited".
     */
    constraints: Record<string, string>
}

export interface WfsFeatureType {
    metadata: Metadata
    /** The advertised qualified name, e.g. "dwd:RBSN_T2m". */
    name: string
    /** Namespace URI the prefix of the name is bound to, undefined for an unprefixed name. */
    namespaceUri?: string
    /** WGS84BoundingBox as [west, south, east, north] in lon/lat degrees. */
    bounds?: [number, number, number, number]
    defaultCrs?: string
    otherCrs: string[]
    /** Per-type OutputFormats; an empty list means the type states none. */
    outputFormats: string[]
    metadataUrl?: string
}

export interface WfsCapabilitites {
    version: string
    metadata: Metadata
    serviceType?: string
    serviceTypeVersions: string[]
    /** Named ows:Constraint entries of the Filter_Capabilities section. */
    filterConstraints: Record<string, string>
    featureTypes: WfsFeatureType[]
    operationUrls: {
        getCapabilities: WfsOperation
        describeFeatureType?: WfsOperation
        getFeature: WfsOperation
    }
}

/**
 * The shared format negotiation rule for WFS (coordinated with the backend):
 * a feature type only overrides the operation-wide GetFeature outputFormat
 * list when it states its own OutputFormats; otherwise the operation-wide
 * advertised tokens apply. Both keep the exact advertised spellings.
 */
export const negotiatedFeatureTypeFormats = (featureType: WfsFeatureType, getFeature: WfsOperation): string[] => {
    return featureType.outputFormats.length > 0 ? featureType.outputFormats : getFeature.mimeTypes
}