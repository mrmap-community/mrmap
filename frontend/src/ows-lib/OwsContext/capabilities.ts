import { OWSResource } from './core';
import { Operation } from './types';
import { isWfsOfferingCode, isWmsOfferingCode } from './validation';

/**
 * Why a resource asks for something this viewer cannot deliver. The viewer renders exactly two
 * combinations: a WMS offering with a GetMap operation offered as GET with an href, and a WFS
 * offering with a GetFeature operation offered as GET with an href, an advertised GeoJSON output
 * format and an advertised WGS 84 CRS. Everything else an offering, an operation method or an
 * inline content offers is reported instead of being dropped in silence, while the supported
 * resources keep rendering.
 */
export type UnsupportedReason =
  | { kind: 'offering'; code: string }
  | { kind: 'method'; code: string; method: string }
  | { kind: 'operation'; code: string }
  | { kind: 'format'; code: string }
  | { kind: 'crs'; code: string }
  | { kind: 'content'; type: string }

/**
 * The GeoJSON media types the viewer can draw on the map directly — the same advertised tokens
 * the backend previews accept as a bounded GetFeature output format.
 */
const GEOJSON_FORMATS = new Set(['application/json', 'application/geo+json', 'json', 'geojson'])

export const isGeoJsonFormat = (format: string): boolean =>
  GEOJSON_FORMATS.has(format.trim().toLowerCase())

/** A CRS token naming WGS 84, exactly as the backend preview recognizes it. */
export const isWgs84CrsToken = (crs: string): boolean =>
  crs.trim().toUpperCase().endsWith(':4326') || crs.trim().toUpperCase().endsWith('/4326')

/**
 * The GetMap operation the viewer can render, or undefined when the resource asks for something
 * else. Alternative WMS offerings resolve explicitly: the first WMS offering decides, the remain-
 * ders of the document are reported by getUnsupportedReasons.
 */
export const getRenderableGetMapOperation = (resource: OWSResource) => {
  const operation = resource.properties.offerings
    ?.find(offering => isWmsOfferingCode(offering.code))
    ?.operations?.find(operation =>
      operation.code === 'GetMap' && String(operation.method ?? '').toLowerCase() === 'get')
  return operation?.href === undefined ? undefined : operation
}

export const isRenderableResource = (resource: OWSResource): boolean =>
  getRenderableGetMapOperation(resource) !== undefined ||
  getRenderableGetFeatureOperation(resource) !== undefined

/**
 * The GetFeature operation the viewer can render a viewport with, together with the GeoJSON
 * output format negotiated for it. Like the WMS resolution the first WFS offering decides; a type
 * without an advertised GeoJSON format or without an advertised WGS 84 CRS has no renderable
 * alternative and is reported by getUnsupportedReasons instead of being requested in vain.
 */
export const getRenderableGetFeatureOperation = (
  resource: OWSResource,
): { operation: Operation; format: string } | undefined => {
  const offering = resource.properties.offerings?.find(offering => isWfsOfferingCode(offering.code))
  if (offering === undefined) return undefined

  const operation = offering.operations?.find(operation =>
    operation.code === 'GetFeature' &&
    String(operation.method ?? '').toLowerCase() === 'get' &&
    typeof operation.href === 'string' &&
    operation.href.length > 0)
  if (operation === undefined) return undefined

  const advertised = Array.isArray(offering.outputFormats)
    ? offering.outputFormats.filter((format): format is string => typeof format === 'string')
    : typeof operation.type === 'string' ? [operation.type] : []
  const format = advertised.find(isGeoJsonFormat)
  if (format === undefined) return undefined

  const crsTokens = [
    ...(typeof offering.defaultCrs === 'string' ? [offering.defaultCrs] : []),
    ...(Array.isArray(offering.otherCrs)
      ? offering.otherCrs.filter((crs): crs is string => typeof crs === 'string') : [])
  ]
  if (!crsTokens.some(isWgs84CrsToken)) return undefined

  return { operation, format }
}

/**
 * The names of everything in the resource the viewer cannot use. A renderable resource answers
 * nothing: its supported GetMap is the resolved alternative to everything else it carries.
 */
export const getUnsupportedReasons = (resource: OWSResource): UnsupportedReason[] => {
  if (isRenderableResource(resource)) return []

  const reasons: UnsupportedReason[] = []
  const offerings = resource.properties.offerings ?? []
  const wmsOffering = offerings.find(offering => isWmsOfferingCode(offering.code))
  const wfsOffering = offerings.find(offering => isWfsOfferingCode(offering.code))

  offerings
    .filter(offering => !isWmsOfferingCode(offering.code) && !isWfsOfferingCode(offering.code))
    .forEach(offering => {
      if (!reasons.some(reason => reason.kind === 'offering' && reason.code === offering.code)) {
        reasons.push({ kind: 'offering', code: offering.code })
      }
      ;(offering.contents ?? []).forEach(content =>
        reasons.push({ kind: 'content', type: content.type }))
    })

  if (wmsOffering !== undefined) {
    wmsOffering.operations
      ?.filter(operation =>
        operation.code === 'GetMap' && String(operation.method ?? '').toLowerCase() !== 'get')
      .forEach(operation =>
        reasons.push({ kind: 'method', code: operation.code, method: String(operation.method ?? '') }))
    ;(wmsOffering.contents ?? []).forEach(content =>
      reasons.push({ kind: 'content', type: content.type }))
  }

  if (wfsOffering !== undefined) {
    const getFeatureOperations = wfsOffering.operations
      ?.filter(operation => operation.code === 'GetFeature') ?? []
    const getFeature = getFeatureOperations.find(operation =>
      String(operation.method ?? '').toLowerCase() === 'get' &&
      typeof operation.href === 'string' && operation.href.length > 0)
    // the first GetFeature decides, exactly like the first offering: what it lacks is named
    if (getFeatureOperations.length > 0 && getFeature === undefined) {
      reasons.push({
        kind: 'method',
        code: 'GetFeature',
        method: String(getFeatureOperations[0].method ?? '')
      })
    } else if (getFeature !== undefined) {
      const advertised = Array.isArray(wfsOffering.outputFormats)
        ? wfsOffering.outputFormats.filter((format): format is string => typeof format === 'string')
        : typeof getFeature.type === 'string' ? [getFeature.type] : []
      const crsTokens = [
        ...(typeof wfsOffering.defaultCrs === 'string' ? [wfsOffering.defaultCrs] : []),
        ...(Array.isArray(wfsOffering.otherCrs)
          ? wfsOffering.otherCrs.filter((crs): crs is string => typeof crs === 'string') : [])
      ]
      if (!advertised.some(isGeoJsonFormat)) {
        reasons.push({ kind: 'format', code: 'GetFeature' })
      } else if (!crsTokens.some(isWgs84CrsToken)) {
        reasons.push({ kind: 'crs', code: 'GetFeature' })
      }
    }
    ;(wfsOffering.contents ?? []).forEach(content =>
      reasons.push({ kind: 'content', type: content.type }))
  }

  // an offering which asks to be taken along without offering a usable render operation at all
  if (reasons.length === 0 && offerings.length > 0) {
    if (wmsOffering !== undefined) reasons.push({ kind: 'operation', code: 'GetMap' })
    if (wfsOffering !== undefined) reasons.push({ kind: 'operation', code: 'GetFeature' })
  }

  return reasons
}

/**
 * Whether the resource itself asks to be rendered: directly through an active GetMap or, without
 * a GetMap to activate at all, through the activation the document gives it.
 */
export const isRequestedByActivation = (resource: OWSResource): boolean =>
  resource.getWmsOperationByCode('GetMap')?.active === true ||
  (resource.getWmsOperationByCode('GetMap') === undefined && resource.properties.active === true)

/**
 * The readable form of a reason; the reason's own members are the translation options, so the
 * i18n entries under "viewerUnsupported" name every kind with its code, method or content type.
 */
export const unsupportedReasonLabel = (
  reason: UnsupportedReason,
  translate: (key: string, options?: Record<string, unknown>) => string,
) => translate(`viewerUnsupported.${reason.kind}`, reason as unknown as Record<string, unknown>)
