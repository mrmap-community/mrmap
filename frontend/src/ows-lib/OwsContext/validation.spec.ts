import { describe, expect, it } from 'vitest'

import { karteRpFeatures } from './tests/data'
import { OWSContextDocument } from './utils'
import { OWS_CONTEXT_CORE_PROFILE, WMS_OFFERING_CODE, validateOwsContext } from './validation'

interface MutableContext {
    [key: string]: unknown
}

const validDocument = (): MutableContext => ({
    type: 'FeatureCollection',
    id: 'https://www.example.org/context/1/',
    properties: {
        lang: 'en',
        title: 'test context',
        updated: '2024-05-03T10:26:38.476Z',
        links: { profiles: [OWS_CONTEXT_CORE_PROFILE] }
    },
    features: [{
        type: 'Feature',
        properties: {
            title: 'Karte RP',
            updated: '2024-05-03T10:26:38.476Z',
            folder: '/0',
            offerings: [{
                code: WMS_OFFERING_CODE,
                operations: [{
                    code: 'GetMap',
                    method: 'GET',
                    href: 'https://www.example.org/wms?LAYERS=karte_rp',
                    active: true
                }]
            }]
        }
    }]
})

const member = (context: MutableContext, memberName: string): MutableContext =>
    context[memberName] as MutableContext

const featuresOf = (context: MutableContext): MutableContext[] =>
    context.features as MutableContext[]

const firstFeatureProperties = (context: MutableContext): MutableContext =>
    member(featuresOf(context)[0], 'properties')

const operationsOf = (context: MutableContext): MutableContext[] =>
    (firstFeatureProperties(context).offerings as MutableContext[])[0].operations as MutableContext[]

const errorPaths = (context: unknown) =>
    validateOwsContext(context)
        .issues
        .filter(issue => issue.severity === 'error')
        .map(issue => issue.path)

describe('validateOwsContext', () => {

    it('accepts a conformant document without any issue', () => {
        const result = validateOwsContext(validDocument())

        expect(result.hasErrors).toBe(false)
        expect(result.issues).toEqual([])
        expect(result.context).toBeDefined()
    })

    it('accepts the features the viewer builds from a WMS', () => {
        const document = { ...validDocument(), features: karteRpFeatures }

        expect(errorPaths(document)).toEqual([])
        expect(validateOwsContext(document).hasErrors).toBe(false)
    })

    it('generates a document which passes the validation', () => {
        const result = validateOwsContext(OWSContextDocument())

        expect(result.hasErrors).toBe(false)
        expect(result.issues).toEqual([])
        expect(result.context?.id.startsWith('urn:uuid:')).toBe(true)
        expect(result.context?.properties.links?.profiles).toContain(OWS_CONTEXT_CORE_PROFILE)
    })

    it('rejects values which are not a context document', () => {
        [null, '[]', 42, [], true].forEach(value => {
            const result = validateOwsContext(value)

            expect(result.hasErrors).toBe(true)
            expect(result.context).toBeUndefined()
            expect(result.issues[0].path).toEqual('document')
        })
    })

    it('rejects documents which are no feature collections', () => {
        const document = { ...validDocument(), type: 'Feature' }

        expect(errorPaths(document)).toEqual(['type'])
    })

    it('reports every missing core metadata member by its path', () => {
        const document = validDocument()
        const properties = member(document, 'properties')
        delete properties.lang
        delete properties.title
        delete properties.updated

        expect(errorPaths(document)).toEqual([
            'properties.lang',
            'properties.title',
            'properties.updated'
        ])
    })

    it('reports malformed timestamps', () => {
        const document = validDocument()
        member(document, 'properties').updated = '03.05.2024'

        expect(errorPaths(document)).toEqual(['properties.updated'])
    })

    it('reports missing resource metadata by the resource path', () => {
        const document = validDocument()
        const features = featuresOf(document)
        features.push({
            type: 'Feature',
            properties: { folder: 'karte' }
        })

        expect(errorPaths(document)).toEqual([
            'features[1].properties.title',
            'features[1].properties.updated',
            'features[1].properties.folder'
        ])
    })

    it('reports missing and malformed operations by the resource path', () => {
        const document = validDocument()
        operationsOf(document).push(
            {},
            { code: 'GetMap', method: 'PATCH', href: '/wms?LAYERS=karte_rp' }
        )

        expect(errorPaths(document)).toEqual([
            'features[0].properties.offerings[0].operations[1].code',
            'features[0].properties.offerings[0].operations[1].method',
            'features[0].properties.offerings[0].operations[1].href',
            'features[0].properties.offerings[0].operations[2].href'
        ])
    })

    it('reports unsupported offerings and operations as warnings', () => {
        const document = validDocument()
        const offerings = firstFeatureProperties(document).offerings as MutableContext[]
        offerings[0].code = 'http://www.opengis.net/spec/owc/1.0/req/wfs'
        offerings.push({
            code: WMS_OFFERING_CODE,
            operations: [{ code: 'GetLegendGraphic', method: 'GET', href: 'https://www.example.org/wms' }]
        })

        const result = validateOwsContext(document)

        expect(result.hasErrors).toBe(false)
        expect(result.issues.map(issue => issue.path)).toEqual([
            'features[0].properties.offerings[0].code',
            'features[0].properties.offerings[1].operations[0].code'
        ])
        // an unsupported offering is kept, it is only not rendered by the viewer
        expect(result.context?.features[0].properties.offerings?.[0].code)
            .toEqual('http://www.opengis.net/spec/owc/1.0/req/wfs')
    })

    it('accepts a resource which activates GetFeatureInfo without GetMap', () => {
        const document = validDocument()
        const operations = operationsOf(document)
        operations.length = 0
        operations.push({
            code: 'GetFeatureInfo',
            method: 'GET',
            href: 'https://www.example.org/wms?QUERY_LAYERS=karte_rp',
            active: false
        })

        const result = validateOwsContext(document)

        expect(result.issues).toEqual([])
        // the independent operation activation of the layer tree is an extension which has to survive
        expect(result.context?.features[0].properties.offerings?.[0].operations?.[0].active).toBe(false)
    })

    it('normalizes a bare uuid identifier into an urn', () => {
        const document = { ...validDocument(), id: '5a2f4c9a-8f0e-4b1e-9c3f-6d2b1a0e7c4d' }

        const result = validateOwsContext(document)

        expect(result.hasErrors).toBe(false)
        expect(result.context?.id).toEqual('urn:uuid:5a2f4c9a-8f0e-4b1e-9c3f-6d2b1a0e7c4d')
        expect(result.issues.map(issue => issue.path)).toEqual(['id'])
    })

    it('adds the core profile reference and keeps the given ones', () => {
        const document = validDocument()
        member(document, 'properties').links = { profiles: ['http://www.example.org/profile/1'] }

        const result = validateOwsContext(document)

        expect(result.hasErrors).toBe(false)
        expect(result.issues.map(issue => issue.path)).toEqual(['properties.links.profiles'])
        expect(result.context?.properties.links?.profiles).toEqual([
            'http://www.example.org/profile/1',
            OWS_CONTEXT_CORE_PROFILE
        ])
    })

    it('maps the language member of mrmap map contexts onto lang', () => {
        const document = validDocument()
        const properties = member(document, 'properties')
        delete properties.lang
        properties.language = 'de'

        const result = validateOwsContext(document)

        expect(result.hasErrors).toBe(false)
        expect(result.context?.properties.lang).toEqual('de')
        expect(result.issues.map(issue => issue.path)).toEqual(['properties.language'])
    })

    it('keeps extension members of the document', () => {
        const document = {
            ...validDocument(),
            authentications: [{ type: 'header', name: 'Authorization', value: 'token' }],
            crs: { type: 'name', properties: { name: 'EPSG:25832' } }
        }

        const result = validateOwsContext(document)

        expect(result.context?.authentications).toEqual(document.authentications)
        expect(result.context?.crs).toEqual(document.crs)
    })

    it('rejects folders the layer tree cannot build', () => {
        const document = validDocument()
        firstFeatureProperties(document).folder = 'karte'

        expect(errorPaths(document)).toEqual(['features[0].properties.folder'])
    })

    it('rejects resources whose parent folder is not part of the document', () => {
        const document = validDocument()
        const features = featuresOf(document)
        features.push({
            type: 'Feature',
            properties: { title: 'child', updated: '2024-05-03T10:26:38.476Z', folder: '/1/0' }
        })

        expect(errorPaths(document)).toEqual(['features[1].properties.folder'])
    })

    it('rejects duplicated folders', () => {
        const document = validDocument()
        const features = featuresOf(document)
        features.push({
            type: 'Feature',
            properties: { title: 'copy', updated: '2024-05-03T10:26:38.476Z', folder: '/0' }
        })

        expect(errorPaths(document)).toEqual(['features[1].properties.folder'])
    })
})
