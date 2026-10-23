import { OWSResource } from './core';
import { isWmsOfferingCode } from './validation';

/**
 * Why a resource asks for something this viewer cannot deliver. The viewer renders exactly one
 * combination: a WMS offering with a GetMap operation offered as GET with an href. Everything else
 * an offering, an operation method or an inline content offers is reported instead of being
 * dropped in silence, while the supported resources keep rendering.
 */
export type UnsupportedReason =
  | { kind: 'offering'; code: string }
  | { kind: 'method'; code: string; method: string }
  | { kind: 'operation'; code: string }
  | { kind: 'content'; type: string }

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
  getRenderableGetMapOperation(resource) !== undefined

/**
 * The names of everything in the resource the viewer cannot use. A renderable resource answers
 * nothing: its supported GetMap is the resolved alternative to everything else it carries.
 */
export const getUnsupportedReasons = (resource: OWSResource): UnsupportedReason[] => {
  if (isRenderableResource(resource)) return []

  const reasons: UnsupportedReason[] = []
  const offerings = resource.properties.offerings ?? []
  const wmsOffering = offerings.find(offering => isWmsOfferingCode(offering.code))

  offerings
    .filter(offering => !isWmsOfferingCode(offering.code))
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

  // an offering which asks to be taken along without offering a usable GetMap at all
  if (reasons.length === 0 && offerings.length > 0) {
    reasons.push({ kind: 'operation', code: 'GetMap' })
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
