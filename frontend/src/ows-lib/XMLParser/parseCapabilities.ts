import moment from 'moment'

import { ElevationDimension, InheritableProperties, Style, TempDimension, TimeDimension, WmsCapabilitites, WmsLayer } from './types'
import { getDocument } from './utils'



const getChild = (parent: Element | Document | undefined, localName: string): Element | undefined => {
  if (!parent) return undefined
  return Array.from(parent.childNodes).find((node): node is Element => {
    return node.nodeType === Node.ELEMENT_NODE && (node as Element).localName === localName
  })
}

const getDescendantByPath = (parent: Element | Document | undefined, path: string[]): Element | undefined => {
  let node: Element | Document | undefined = parent
  for (const name of path) {
    if (!node) return undefined
    node = getChild(node, name)
  }
  return node instanceof Element ? node : undefined
}

const getText = (parent: Element | Document | undefined, ...path: string[]): string | undefined => {
  const node = getDescendantByPath(parent, path)
  return node?.textContent?.trim() || undefined
}

const getAttribute = (element: Element | undefined, ...names: string[]): string | undefined => {
  if (!element) return undefined
  for (const name of names) {
    const value = element.getAttribute(name)
    if (value !== null) return value
  }
  return undefined
}

const parseLayerMetrics = {
  count: 0,
  totalMs: 0
}

const toBounds = (values: (string | null | undefined)[]): [number, number, number, number] | undefined => {
  const bounds = values.map(value => value === null || value === undefined ? NaN : Number(value))
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

export const parseTimeDimension = (timeDimension: Element): TimeDimension | undefined => {
  const dimensionValue = timeDimension.textContent?.trim()
  if (!dimensionValue) return undefined

  const [start, stop, resolution] = dimensionValue.split('/')
  return {
    start: new Date(start),
    stop: stop ? new Date(stop) : undefined,
    resolution: resolution ? moment.duration(resolution) : undefined
  }
}

export const parseDimension = (dimension: Element): TimeDimension | TempDimension | ElevationDimension | undefined => {
  const type = getAttribute(dimension, 'name')
  const units = getAttribute(dimension, 'units')
  const value = dimension.textContent?.trim() ?? ''

  if (type === 'time' && units === 'ISO8601') {
    const [start, stop, resolution] = value.split('/')
    return {
      start: new Date(start),
      stop: stop ? new Date(stop) : undefined,
      resolution: resolution ? moment.duration(resolution) : undefined
    }
  }

  if (type === 'temperature') {
    return {
      unit: units ?? '',
      unitSymbol: getAttribute(dimension, 'unitSymbol') ?? '',
      default: Number(getAttribute(dimension, 'default') ?? 0),
      values: value.split('/').map(v => Number(v))
    }
  }

  if (type === 'elevation') {
    return {
      crs: units ?? '',
      unitSymbol: getAttribute(dimension, 'unitSymbol') ?? '',
      default: getAttribute(dimension, 'default') ?? '',
      values: value.split('/').map(v => Number(v))
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

export const parseLayer = (
  layer: Element,
  inherited?: InheritableProperties
): WmsLayer => {
  const layerStart = performance.now()
  parseLayerMetrics.count += 1

  let abstract: string | undefined
  const srsValues: string[] = []
  const crsValues: string[] = []
  const declaredStyles: Style[] = []
  const declaredDimensions: (TimeDimension | TempDimension | ElevationDimension)[] = []
  let minScaleDenominator: string | undefined
  let maxScaleDenominator: string | undefined
  let bboxElement: Element | undefined
  const sublayers: Element[] = []

  for (const child of Array.from(layer.children)) {
    switch (child.localName) {
      case 'Abstract':
        abstract = child.textContent?.trim() || undefined
        break
      case 'SRS':
        srsValues.push(child.textContent?.trim() || '')
        break
      case 'CRS':
        crsValues.push(child.textContent?.trim() || '')
        break
      case 'Style':
        declaredStyles.push(parseStyle(child))
        break
      case 'Dimension': {
        const dimension = parseDimension(child)
        if (dimension) declaredDimensions.push(dimension)
        break
      }
      case 'MinScaleDenominator':
        minScaleDenominator = child.textContent?.trim() || undefined
        break
      case 'MaxScaleDenominator':
        maxScaleDenominator = child.textContent?.trim() || undefined
        break
      case 'EX_GeographicBoundingBox':
      case 'LatLonBoundingBox':
        bboxElement = child
        break
      case 'Layer':
        sublayers.push(child)
        break
    }
  }

  // WMS 1.1.1 states all reference systems of a layer whitespace separated in one "SRS" element,
  // WMS 1.3.0 one "CRS" element per reference system.
  const declaredReferenceSystems = (srsValues.length > 0 ? srsValues : crsValues)
    .flatMap(value => value.split(/\s+/))
    .filter(Boolean)

  // Reference systems and styles are inherited and added to; a style which repeats the name of an
  // inherited style replaces that inherited definition. Every other setting the layer states
  // replaces the inherited value - including "0" and false - and is inherited wherever the layer
  // does not state it.
  const referenceSystems = [...new Set([
    ...(inherited?.referenceSystems ?? []),
    ...declaredReferenceSystems
  ])]
  const styles = [...new Map([...(inherited?.styles ?? []), ...declaredStyles]
    .map(style => [style.metadata.name, style] as [string, Style])).values()]
  const dimensions = declaredDimensions.length > 0 ? declaredDimensions : inherited?.dimension
  const bbox = getLayerBoundsFromBbox(bboxElement) ?? inherited?.bbox
  const minScaleDenominatorValue = parseScaleDenominator(minScaleDenominator) ?? inherited?.minScaleDenominator
  const maxScaleDenominatorValue = parseScaleDenominator(maxScaleDenominator) ?? inherited?.maxScaleDenominator
  const isQueryable = parseLayerAttribute(layer, 'queryable') ?? inherited?.isQueryable
  const isOpaque = parseLayerAttribute(layer, 'opaque') ?? inherited?.isOpaque
  const isCascaded = parseLayerAttribute(layer, 'cascaded') ?? inherited?.isCascaded

  // these resolved settings are what the children of this layer inherit
  const inheritable: InheritableProperties = {
    referenceSystems,
    styles,
    ...(bbox && { bbox }),
    ...(dimensions && { dimension: dimensions }),
    ...(minScaleDenominatorValue !== undefined && { minScaleDenominator: minScaleDenominatorValue }),
    ...(maxScaleDenominatorValue !== undefined && { maxScaleDenominator: maxScaleDenominatorValue }),
    ...(isQueryable !== undefined && { isQueryable }),
    ...(isOpaque !== undefined && { isOpaque }),
    ...(isCascaded !== undefined && { isCascaded })
  }

  const layerObj: WmsLayer = {
    metadata: {
      title: getText(layer, 'Title') ?? '',
      name: getText(layer, 'Name') ?? '',
      ...(abstract ? { abstract } : {})
    },
    ...(referenceSystems.length > 0 && { referenceSystems }),
    ...(dimensions && dimensions.length > 0 && { dimension: dimensions }),
    ...(bbox && { bbox }),
    ...(styles.length > 0 && { styles }),
    ...(minScaleDenominatorValue !== undefined && { minScaleDenominator: minScaleDenominatorValue }),
    ...(maxScaleDenominatorValue !== undefined && { maxScaleDenominator: maxScaleDenominatorValue }),
    ...(isQueryable !== undefined && { isQueryable }),
    ...(isOpaque !== undefined && { isOpaque }),
    ...(isCascaded !== undefined && { isCascaded })
  }

  if (sublayers.length > 0) {
    layerObj.children = sublayers.map(child => parseLayer(child, inheritable))
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
