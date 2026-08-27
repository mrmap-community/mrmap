import { Polygon } from 'geojson'
import moment from 'moment'

import { ElevationDimension, Style, TempDimension, TimeDimension, WmsCapabilitites, WmsLayer } from './types'
import { getDocument } from './utils'



const getChild = (parent: Element | Document | undefined, localName: string): Element | undefined => {
  if (!parent) return undefined
  return Array.from(parent.childNodes).find((node): node is Element => {
    return node.nodeType === Node.ELEMENT_NODE && (node as Element).localName === localName
  })
}

const getChildren = (parent: Element | Document | undefined, localName: string): Element[] => {
  if (!parent) return []
  return Array.from(parent.childNodes).filter((node): node is Element => {
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

export const getExtentFromPolygonBbox = (
  bbox: Polygon[] | undefined,
  inherited?: [number, number, number, number]
): [number, number, number, number] | undefined => {
  if (!bbox || bbox.length === 0) {
    return inherited
  }

  const coords = bbox[0].coordinates?.[0] as [number, number][] | undefined
  if (!coords || coords.length < 4) {
    return inherited
  }

  const xs = coords.map(([x]) => x)
  const ys = coords.map(([, y]) => y)

  return [
    Math.min(...xs),
    Math.min(...ys),
    Math.max(...xs),
    Math.max(...ys),
  ]
}

export const getLayerBoundsFromBbox = (
  bboxElement: Element | undefined
): [number, number, number, number] | undefined => {
  if (!bboxElement) return undefined

  const west = Number(getText(bboxElement, 'westBoundLongitude'))
  const south = Number(getText(bboxElement, 'southBoundLatitude'))
  const east = Number(getText(bboxElement, 'eastBoundLongitude'))
  const north = Number(getText(bboxElement, 'northBoundLatitude'))

  if ([west, south, east, north].some(value => !Number.isFinite(value))) {
    return undefined
  }

  return [west, south, east, north]
}

export const layerBboxToGeoJSON = (
  bboxElement: Element | undefined
): Polygon[] | undefined => {
  const bounds = getLayerBoundsFromBbox(bboxElement)
  if (!bounds) return undefined

  const [west, south, east, north] = bounds

  return [{
    type: 'Polygon',
    coordinates: [[
      [west, south],
      [east, south],
      [east, north],
      [west, north],
      [west, south]
    ]]
  }] as unknown as Polygon[]
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
  inheritedExtent?: [number, number, number, number]
): WmsLayer => {
  const layerStart = performance.now()
  parseLayerMetrics.count += 1

  let abstract: string | undefined
  const srsValues: string[] = []
  const crsValues: string[] = []
  const styles: Style[] = []
  const dimensions: (TimeDimension | TempDimension | ElevationDimension)[] = []
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
        styles.push(parseStyle(child))
        break
      case 'Dimension': {
        const dimension = parseDimension(child)
        if (dimension) dimensions.push(dimension)
        break
      }
      case 'MinScaleDenominator':
        minScaleDenominator = child.textContent?.trim() || undefined
        break
      case 'MaxScaleDenominator':
        maxScaleDenominator = child.textContent?.trim() || undefined
        break
      case 'EX_GeographicBoundingBox':
        bboxElement = child
        break
      case 'Layer':
        sublayers.push(child)
        break
    }
  }
  
  const rawBbox = bboxElement ? layerBboxToGeoJSON(bboxElement) : undefined
  const effectiveExtent = getExtentFromPolygonBbox(rawBbox, inheritedExtent)

  const crs = srsValues.length > 0 ? srsValues : crsValues
  const isQueryable = getAttribute(layer, 'queryable')
  const isOpaque = getAttribute(layer, 'opaque')
  const isCascaded = getAttribute(layer, 'cascaded')

  const layerObj: WmsLayer = {
    metadata: {
      title: getText(layer, 'Title') ?? '',
      name: getText(layer, 'Name') ?? '',
      ...(abstract ? { abstract } : {})
    },
    ...(crs.length > 0 && { referenceSystems: crs }),
    ...(dimensions.length > 0 && { dimension: dimensions }),
    ...(effectiveExtent && { bbox: effectiveExtent }),
    ...(styles.length > 0 && { styles }),
    ...(minScaleDenominator ? { minScaleDenominator: Number(minScaleDenominator) } : {}),
    ...(maxScaleDenominator ? { maxScaleDenominator: Number(maxScaleDenominator) } : {}),
    ...(isQueryable ? { isQueryable: Boolean(Number(isQueryable)) } : {}),
    ...(isOpaque ? { isQpaque: Boolean(Number(isOpaque)) } : {}),
    ...(isCascaded ? { isCascaded: Boolean(Number(isCascaded)) } : {})
  }


  if (sublayers.length > 0) {
    layerObj.children = sublayers.map(child => parseLayer(child, effectiveExtent))
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
      getFeatureInfo: findOperationUrl(root, 'GetFeatureInfo')
    },
    rootLayer: parseLayer(rootLayerElement ?? root)
  }

  parseWmsTimings.rootLayer = performance.now() - getDocumentStart - parseWmsTimings.getDocument
  parseWmsTimings.layerCount = parseLayerMetrics.count
  parseWmsTimings.parseLayerTotal = parseLayerMetrics.totalMs
  parseWmsTimings.total = performance.now() - totalStart

  return capabilities
}
