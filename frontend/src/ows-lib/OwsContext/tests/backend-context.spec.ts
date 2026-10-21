import { describe, expect, test } from 'vitest'

import { OWSContext, OWSResource } from '../core'
import { OWSContext as IOWSContext } from '../types'
import { validateOwsContext, WMS_OFFERING_CODE } from '../validation'
import backendContext from './backend-context.json'

const importContext = (document: unknown) => {
    const validated = validateOwsContext(document)
    expect(validated.hasErrors, JSON.stringify(validated.issues)).toBe(false)
    return OWSContext.fromPlainObject(validated.context!)
}

const operationUrls = (context: OWSContext, code: string) => context.getOptimizedUrlsByCode(
    code, feature => feature.getWmsOperationByCode(code)?.active === true
)

test('consumes a backend GeoJSON context and retains hierarchy, styles and independent selection on round trip', () => {
    const context = importContext(backendContext)
    expect(validateOwsContext(backendContext).issues).toEqual([])
    expect(context.features.map(feature => feature.properties.folder)).toEqual(['/0', '/0/0', '/0/1'])
    expect(context.treeify()[0].children.map(child => child.properties.title)).toEqual(['Styled layer', 'Sibling'])
    expect(context.properties.authors).toEqual([{ name: 'Map author' }])
    expect(operationUrls(context, 'GetMap')).toHaveLength(0)
    expect(operationUrls(context, 'GetFeatureInfo')[0].url.hostname).toBe('selection.example')
    const roundTrip = importContext(JSON.parse(JSON.stringify(context)))
    expect(roundTrip.features.map(feature => feature.properties)).toEqual(context.features.map(feature => feature.properties))
    const layer = roundTrip.features[1]
    expect(layer.properties.minscaledenominator).toBe(0)
    expect(layer.properties.maxscaledenominator).toBe(50000)
    expect(layer.getWmsOffering()?.styles?.[0].name).toBe('configured')
    layer.getWmsOperationByCode('GetMap')!.active = true
    layer.getWmsOperationByCode('GetFeatureInfo')!.active = false
    expect(operationUrls(roundTrip, 'GetMap')[0].url.searchParams.get('STYLES')).toBe('configured')
    expect(operationUrls(roundTrip, 'GetFeatureInfo')).toHaveLength(0)
})

describe.each([
    'http://www.opengis.net/spec/owc/1.0/req/wms',
    'http://www.opengis.net/spec/owc-atom/1.0/req/wms'
])('legacy offering %s', code => {
    test('normalizes known aliases and split offerings without mutating the source', () => {
        const document = JSON.parse(JSON.stringify(backendContext))
        document.properties.language = document.properties.lang
        delete document.properties.lang
        document.properties.subtilte = document.properties.subtitle
        delete document.properties.subtitle
        const feature = document.features[1]
        feature.properties.minScaleDenominator = 0
        delete feature.properties.minscaledenominator
        feature.offerings = feature.properties.offerings[0].operations.map((operation: unknown) => ({ code, operations: [operation] }))
        delete feature.properties.offerings
        const before = JSON.stringify(document)
        const context = importContext(document)
        expect(JSON.stringify(document)).toBe(before)
        expect(context.properties.lang).toBe('en')
        expect(context.properties.subtitle).toBe(backendContext.properties.subtitle)
        expect(context.features[1].properties.offerings).toHaveLength(1)
        expect(context.features[1].getWmsOffering()?.code).toBe(WMS_OFFERING_CODE)
        expect(operationUrls(context, 'GetFeatureInfo')).toHaveLength(1)
        expect(context.features[1].properties.minscaledenominator).toBe(0)
        expect(validateOwsContext(JSON.parse(JSON.stringify(context))).hasErrors).toBe(false)
    })

    test('supports direct model construction with the previous offering identifier', () => {
        const resource = OWSResource.fromPlainObject(backendContext.features[1] as unknown as IOWSContext['features'][number])
        resource.properties.offerings![0].code = code
        expect(resource.getWmsOperationByCode('GetFeatureInfo')?.active).toBe(true)
    })
})

test('rejects legacy documents whose empty dates or duplicate paths cannot be recovered', () => {
    const document = JSON.parse(JSON.stringify(backendContext))
    document.properties.updated = ''
    document.features[1].properties.folder = '/0'
    const result = validateOwsContext(document)
    expect(result.hasErrors).toBe(true)
    expect(result.issues.some(issue => issue.path === 'properties.updated')).toBe(true)
    expect(result.issues.some(issue => issue.message.includes('duplicates'))).toBe(true)
})
