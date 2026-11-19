import { parseDuration } from '../iso8601'
import { AdvertisedDimension, ElevationDimension, InheritableProperties, Style, TempDimension, TimeDimension, WmsCapabilitites, WmsLayer } from './types'
import { getAttribute, getDescendantByPath, getDocument, getChild, getText } from './utils'


const parseLayerMetrics = {
  count: 0,
  totalMs: 0
}

const toBounds = (values: (string | null | undefined)[]): [number, number, number, number] | undefined => {
  const bounds = values.map(value => value === null || value === undefined ? Number.NaN : Number(value))
  if (bounds.some(value => !Number.isFinite(value))) {
    return undefined
  }
  return bounds as [number, number, number, number]
}

/**
 * Geographic extent of a layer, described by an "EX_GeographicBoundingBox" element in WMS 1.3.0 and
 * by a "LatLonBoundingBox" element in WMS 1.1.1. Both elements are defined in geographic (lon/lat)
 * coordinates, so the result is the same tuple shape for every supported WMS version.
 */
export const getLayerBoundsFromBbox = (
  bboxElement: Element | undefined
): [number, number, number, number] | undefined => {
  if (!bboxElement) return undefined

  if (bboxElement.localName === 'LatLonBoundingBox') {
    return toBounds(['minx', 'miny', 'maxx', 'maxy'].map(name => bboxElement.getAttribute(name)))
  }

  return toBounds(['westBoundLongitude', 'southBoundLatitude', 'eastBoundLongitude', 'northBoundLatitude']
    .map(name => getText(bboxElement, name)))
}

/**
 * WMS states the layer attributes "queryable", "opaque" and "cascaded" as "0" or "1". A stated
 * attribute overrides the inherited value, a missing attribute inherits; "0" therefore means false
 * and not "not stated".
 */
const parseLayerAttribute = (layer: Element, name: string): boolean | undefined => {
  const value = getAttribute(layer, name)
  if (value === undefined) return undefined
  return value === '1' || value.toLowerCase() === 'true'
}

/**
 * Scale denominators follow the WMS scale type which allows "infinity" next to a decimal number. A
 * value which cannot be read is treated as not stated, so the layer keeps its inherited value.
 */
const parseScaleDenominator = (value: string | undefined): number | undefined => {
  if (value === undefined) return undefined
  const parsed = Number(value)
  return Number.isNaN(parsed) ? undefined : parsed
}

/**
 * The time dimension the value text of a `Dimension` element names: its first observation, its last
 * one when the range states one, and the duration between the observations. The two instants are read
 * as the `Date` of the stated text, as they have always been read here, while a resolution outside
 * the ISO 8601 grammar of a WMS duration is answered by nothing.
 */
const parseTimeDimensionValue = (value: string): TimeDimension => {
  const [start, stop, resolution] = value.split('/')
  return {
    start: new Date(start),
    stop: stop ? new Date(stop) : undefined,
    resolution: resolution ? parseDuration(resolution) : undefined
  }
}

export const parseTimeDimension = (timeDimension: Element): TimeDimension | undefined => {
  const dimensionValue = timeDimension.textContent?.trim()
  if (!dimensionValue) return undefined

  return parseTimeDimensionValue(dimensionValue)
}

export const parseDimension = (dimension: Element): TimeDimension | TempDimension | ElevationDimension | undefined => {
  const type = getAttribute(dimension, 'name')
  const units = getAttribute(dimension, 'units')
  const value = dimension.textContent?.trim() ?? ''

  if (type === 'time' && units === 'ISO8601') {
    return parseTimeDimensionValue(value)
  }

  if (type === 'temperature') {
    return {
      unit: units ?? '',
      unitSymbol: getAttribute(dimension, 'unitSymbol') ?? '',
      default: Number(getAttribute(dimension, 'default') ?? 0),
      values: value.split('/').map(Number)
    }
  }

  if (type === 'elevation') {
    return {
      crs: units ?? '',
      unitSymbol: getAttribute(dimension, 'unitSymbol') ?? '',
      default: getAttribute(dimension, 'default') ?? '',
      values: value.split('/').map(Number)
    }
  }

  return undefined
}

export const parseStyle = (style: Element): Style => {
  const legendUrlElement = getChild(style, 'LegendURL')
  const onlineResource = getChild(legendUrlElement, 'OnlineResource')
  const hrefString = onlineResource ? getAttribute(onlineResource, 'href', 'xlink:href') : undefined
  const hrefUrl = hrefString ? new URL(hrefString) : undefined

  return {
    metadata: {
      name: getText(style, 'Name') ?? '',
      title: getText(style, 'Title') ?? '',
      abstract: getText(style, 'Abstract') ?? undefined
    },
    legendUrl: onlineResource && hrefUrl
      ? {
          mimeType: getText(legendUrlElement, 'Format') ?? '',
          href: hrefUrl,
          width: Number(getAttribute(legendUrlElement, 'width') ?? getAttribute(legendUrlElement, '_width') ?? 0),
          height: Number(getAttribute(legendUrlElement, 'height') ?? getAttribute(legendUrlElement, '_height') ?? 0)
        }
      : undefined
  }
}

export const forceArray = <T>(obj: T | T[] | undefined): T[] => {
  if (obj === undefined) return []
  return Array.isArray(obj) ? obj : [obj]
}

/** everything a layer element carries among its direct children, collected while walking them */
interface DeclaredLayerMembers {
  abstract?: string
  srsValues: string[]
  crsValues: string[]
  styles: Style[]
  dimensions: (TimeDimension | TempDimension | ElevationDimension)[]
  advertisedDimensions: AdvertisedDimension[]
  minScaleDenominator?: string
  maxScaleDenominator?: string
  bboxElement?: Element
  sublayers: Element[]
}

/** record one direct child of a layer among the members it declares; a Dimension child is a
 *  structured dimension and an advertised one whenever it names its values */
const collectLayerMember = (child: Element, declared: DeclaredLayerMembers) => {
  switch (child.localName) {
    case 'Abstract':
      declared.abstract = child.textContent?.trim() || undefined
      break
    case 'SRS':
      declared.srsValues.push(child.textContent?.trim() || '')
      break
    case 'CRS':
      declared.crsValues.push(child.textContent?.trim() || '')
      break
    case 'Style':
      declared.styles.push(parseStyle(child))
      break
    case 'Dimension': {
      const dimension = parseDimension(child)
      if (dimension) declared.dimensions.push(dimension)
      const name = getAttribute(child, 'name')
      const values = child.textContent?.trim() ?? ''
      if (name && values) {
        const units = getAttribute(child, 'units')
        const unitSymbol = getAttribute(child, 'unitSymbol')
        const defaultValue = getAttribute(child, 'default')
        declared.advertisedDimensions.push({
          name,
          values,
          ...(units !== undefined && { units }),
          ...(unitSymbol !== undefined && { unitSymbol }),
          ...(defaultValue !== undefined && { default: defaultValue })
        })
      }
      break
    }
    case 'MinScaleDenominator':
      declared.minScaleDenominator = child.textContent?.trim() || undefined
      break
    case 'MaxScaleDenominator':
      declared.maxScaleDenominator = child.textContent?.trim() || undefined
      break
    case 'EX_GeographicBoundingBox':
    case 'LatLonBoundingBox':
      declared.bboxElement = child
      break
    case 'Layer':
      declared.sublayers.push(child)
      break
  }
}

/** the layer's settings resolved against its parent: what the layer states replaces the inherited
 *  value - including "0" and false - and is inherited wherever the layer does not state it */
const resolveLayerSettings = (layer: Element, declared: DeclaredLayerMembers, inherited?: InheritableProperties) => {
  // WMS 1.1.1 states all reference systems of a layer whitespace separated in one "SRS" element,
  // WMS 1.3.0 one "CRS" element per reference system.
  const declaredReferenceSystems = (declared.srsValues.length > 0 ? declared.srsValues : declared.crsValues)
    .flatMap(value => value.split(/\s+/))
    .filter(Boolean)

  // Reference systems and styles are inherited and added to; a style which repeats the name of an
  // inherited style replaces that inherited definition.
  return {
    referenceSystems: [...new Set([
      ...(inherited?.referenceSystems ?? []),
      ...declaredReferenceSystems
    ])],
    styles: [...new Map([...(inherited?.styles ?? []), ...declared.styles]
      .map(style => [style.metadata.name, style] as [string, Style])).values()],
    dimensions: declared.dimensions.length > 0 ? declared.dimensions : inherited?.dimension,
    // A dimension a layer states replaces the inherited dimension of the same name; the others stay inherited.
    advertisedDimensions: [...new Map([
      ...(inherited?.advertisedDimension ?? []),
      ...declared.advertisedDimensions
    ].map(dimension => [dimension.name.toLowerCase(), dimension] as [string, AdvertisedDimension])).values()],
    bbox: getLayerBoundsFromBbox(declared.bboxElement) ?? inherited?.bbox,
    minScaleDenominator: parseScaleDenominator(declared.minScaleDenominator) ?? inherited?.minScaleDenominator,
    maxScaleDenominator: parseScaleDenominator(declared.maxScaleDenominator) ?? inherited?.maxScaleDenominator,
    isQueryable: parseLayerAttribute(layer, 'queryable') ?? inherited?.isQueryable,
    isOpaque: parseLayerAttribute(layer, 'opaque') ?? inherited?.isOpaque,
    isCascaded: parseLayerAttribute(layer, 'cascaded') ?? inherited?.isCascaded
  }
}

type ResolvedLayerSettings = ReturnType<typeof resolveLayerSettings>

/** the settings a layer hands on to its children: everything it resolved, stated or inherited */
const inheritableOf = (resolved: ResolvedLayerSettings): InheritableProperties => ({
  referenceSystems: resolved.referenceSystems,
  styles: resolved.styles,
  ...(resolved.bbox && { bbox: resolved.bbox }),
  ...(resolved.dimensions && { dimension: resolved.dimensions }),
  ...(resolved.advertisedDimensions.length > 0 && { advertisedDimension: resolved.advertisedDimensions }),
  ...(resolved.minScaleDenominator !== undefined && { minScaleDenominator: resolved.minScaleDenominator }),
  ...(resolved.maxScaleDenominator !== undefined && { maxScaleDenominator: resolved.maxScaleDenominator }),
  ...(resolved.isQueryable !== undefined && { isQueryable: resolved.isQueryable }),
  ...(resolved.isOpaque !== undefined && { isOpaque: resolved.isOpaque }),
  ...(resolved.isCascaded !== undefined && { isCascaded: resolved.isCascaded })
})

/** the WMS properties of the layer itself: only what it actually carries is kept */
const wmsPropertiesOf = (resolved: ResolvedLayerSettings): Omit<WmsLayer, 'metadata'> => ({
  ...(resolved.referenceSystems.length > 0 && { referenceSystems: resolved.referenceSystems }),
  ...(resolved.dimensions !== undefined && resolved.dimensions.length > 0 && { dimension: resolved.dimensions }),
  ...(resolved.advertisedDimensions.length > 0 && { advertisedDimension: resolved.advertisedDimensions }),
  ...(resolved.bbox && { bbox: resolved.bbox }),
  ...(resolved.styles.length > 0 && { styles: resolved.styles }),
  ...(resolved.minScaleDenominator !== undefined && { minScaleDenominator: resolved.minScaleDenominator }),
  ...(resolved.maxScaleDenominator !== undefined && { maxScaleDenominator: resolved.maxScaleDenominator }),
  ...(resolved.isQueryable !== undefined && { isQueryable: resolved.isQueryable }),
  ...(resolved.isOpaque !== undefined && { isOpaque: resolved.isOpaque }),
  ...(resolved.isCascaded !== undefined && { isCascaded: resolved.isCascaded })
})

export const parseLayer = (
  layer: Element,
  inherited?: InheritableProperties
): WmsLayer => {
  const layerStart = performance.now()
  parseLayerMetrics.count += 1

  const declared: DeclaredLayerMembers = {
    srsValues: [],
    crsValues: [],
    styles: [],
    dimensions: [],
    advertisedDimensions: [],
    sublayers: []
  }
  for (const child of Array.from(layer.children)) {
    collectLayerMember(child, declared)
  }

  const resolved = resolveLayerSettings(layer, declared, inherited)

  const layerObj: WmsLayer = {
    metadata: {
      title: getText(layer, 'Title') ?? '',
      name: getText(layer, 'Name') ?? '',
      ...(declared.abstract ? { abstract: declared.abstract } : {})
    },
    ...wmsPropertiesOf(resolved)
  }

  if (declared.sublayers.length > 0) {
    // these resolved settings are what the children of this layer inherit
    layerObj.children = declared.sublayers.map(child => parseLayer(child, inheritableOf(resolved)))
  }

  parseLayerMetrics.totalMs += performance.now() - layerStart
  return layerObj
}

const findOperationUrl = (root: Element, operationName: string): { mimeTypes: string[]; get: string; post?: string } => {
  const request = getDescendantByPath(root, ['Capability', 'Request', operationName])
  const formatNode = getChild(request, 'Format')
  const httpNode = getDescendantByPath(request, ['DCPType', 'HTTP'])
  const getNode = getDescendantByPath(httpNode, ['Get', 'OnlineResource'])
  const postNode = getDescendantByPath(httpNode, ['Post', 'OnlineResource'])

  return {
    mimeTypes: formatNode ? forceArray(formatNode.textContent?.trim()).filter(Boolean) : [],
    get: getNode ? getAttribute(getNode, 'href', 'xlink:href') ?? '' : '',
    post: postNode ? getAttribute(postNode, 'href', 'xlink:href') ?? undefined : undefined
  }
}

/**
 * GetFeatureInfo is an optional WMS operation. Capabilities which do not request it shall not be
 * described by an operation with an empty href, so that callers tell both cases apart by checking
 * the member instead of building a URL from nothing.
 */
const findOptionalOperationUrl = (root: Element, operationName: string) => {
  const operation = findOperationUrl(root, operationName)
  return operation.get === '' ? undefined : operation
}

export const parseWms = (xml: string): WmsCapabilitites => {
  const parseWmsTimings = {
    getDocument: 0,
    rootLayer: 0,
    total: 0,
    layerCount: 0,
    parseLayerTotal: 0
  }
  parseLayerMetrics.count = 0
  parseLayerMetrics.totalMs = 0
  const totalStart = performance.now()

  const getDocumentStart = performance.now()
  const document = getDocument(xml)
  parseWmsTimings.getDocument = performance.now() - getDocumentStart

  const root = document.documentElement
  const rootLayerElement = getDescendantByPath(root, ['Capability', 'Layer'])
  if (!rootLayerElement) {
    throw new Error('Root WMS layer element not found')
  }

  const capabilities = {
    version: getAttribute(root, 'version') ?? '',
    metadata: {
      name: getText(root, 'Service', 'Name') ?? '',
      title: getText(root, 'Service', 'Title') ?? '',
      abstract: getText(root, 'Service', 'Abstract') ?? undefined
    },
    operationUrls: {
      getCapabilities: findOperationUrl(root, 'GetCapabilities'),
      getMap: findOperationUrl(root, 'GetMap'),
      getFeatureInfo: findOptionalOperationUrl(root, 'GetFeatureInfo')
    },
    rootLayer: parseLayer(rootLayerElement ?? root)
  }

  parseWmsTimings.rootLayer = performance.now() - getDocumentStart - parseWmsTimings.getDocument
  parseWmsTimings.layerCount = parseLayerMetrics.count
  parseWmsTimings.parseLayerTotal = parseLayerMetrics.totalMs
  parseWmsTimings.total = performance.now() - totalStart

  return capabilities
}
