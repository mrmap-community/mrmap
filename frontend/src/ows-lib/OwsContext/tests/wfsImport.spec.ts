import { describe, expect, it } from 'vitest'

import { parseWfs } from '../../XMLParser/parseWfs'
import capabilitiesInherited from '../../XMLParser/tests/capabilities_inherited_130.xml?raw'
import dwdCapabilities from '../../XMLParser/tests/wfs_2_0_0_dwd.xml?raw'
import mapServerCapabilities from '../../XMLParser/tests/wfs_2_0_0_mapserver.xml?raw'
import minimalCapabilities from '../../XMLParser/tests/wfs_minimal_2_0_0.xml?raw'
import prefixVariantCapabilities from '../../XMLParser/tests/wfs_prefix_variant_2_0_0.xml?raw'
import { WfsCapabilitites, negotiatedFeatureTypeFormats } from '../../XMLParser/types'
import { OWSContext, OWSResource } from '../core'
import { wfsToOWSResources } from '../utils'
import { normalizeResourceProperties, validateOwsContext, WFS_OFFERING_CODE } from '../validation'

const GET_CAPABILITIES_HREF = 'https://www.example.org/wfs?SERVICE=WFS&REQUEST=GetCapabilities'

/** all resources of the imported capabilities, indexed by the qualified name of their feature type */
const featuresByName = (capabilities: WfsCapabilitites) =>
    new Map<string, OWSResource>(wfsToOWSResources(GET_CAPABILITIES_HREF, capabilities)
        .map(feature => [feature.getWfsOffering()?.qualifiedName as string, feature]))

const getFeatureUrl = (feature: OWSResource | undefined, method: string = 'GET') => {
    const href = feature?.getWfsOperationByCode('GetFeature', method)?.href
    return href === undefined ? undefined : new URL(href)
}

describe('wfsToOWSResources', () => {

    describe('with the DWD WFS 2.0.0 capabilities', () => {

        const capabilities = parseWfs(dwdCapabilities)
        const features = featuresByName(capabilities)
        const root = wfsToOWSResources(GET_CAPABILITIES_HREF, capabilities)[0]

        it('builds a service root and one leaf per feature type with valid folders', () => {
            const resources = wfsToOWSResources(GET_CAPABILITIES_HREF, capabilities)

            expect(resources[0].properties.folder).toBe('/0')
            expect(root.properties.title).toBe('DWD GeoServer WFS')
            expect(root.getWfsOffering()?.operations?.[0].code).toBe('GetCapabilities')
            expect(root.getWfsOffering()?.version).toBe('2.0.0')
            expect(resources.slice(1).every((resource, index) =>
                resource.properties.folder === `/0/${index}`)).toBe(true)
            expect(resources.length).toBe(capabilities.featureTypes.length + 1)
        })

        it('preserves qualified type, namespace, bounds, version and CRS on the resource', () => {
            const feature = features.get('dwd:RBSN_T2m')
            const offering = feature?.getWfsOffering()

            expect(feature?.bbox).toEqual([6.02439799999999, 47.398578, 14.950565, 55.010987])
            expect(offering?.qualifiedName).toBe('dwd:RBSN_T2m')
            expect(offering?.namespace).toBe('http://www.dwd.de')
            expect(offering?.version).toBe('2.0.0')
            expect(offering?.defaultCrs).toBe('urn:ogc:def:crs:EPSG::4258')
            expect(offering?.otherCrs).toEqual(capabilities.featureTypes
                .find(type => type.name === 'dwd:RBSN_T2m')?.otherCrs)
        })

        it('builds a GetFeature request with the advertised tokens per type', () => {
            const url = getFeatureUrl(features.get('dwd:RBSN_T2m'))

            expect(`${url?.origin}${url?.pathname}`).toBe('https://maps.dwd.de/geoserver/wfs')
            expect(url?.searchParams.get('SERVICE')).toBe('WFS')
            expect(url?.searchParams.get('REQUEST')).toBe('GetFeature')
            expect(url?.searchParams.get('VERSION')).toBe('2.0.0')
            expect(url?.searchParams.get('TYPENAME')).toBe('dwd:RBSN_T2m')
            expect(url?.searchParams.get('SRSNAME')).toBe('urn:ogc:def:crs:EPSG::4258')
            // the type states no own OutputFormats, so the operation wide advertised ones apply
            expect(url?.searchParams.get('OUTPUTFORMAT'))
                .toBe(capabilities.operationUrls.getFeature.mimeTypes[0])
        })

        it('keeps the advertised POST binding as an operation the viewer does not execute', () => {
            const postUrl = getFeatureUrl(features.get('dwd:RBSN_T2m'), 'POST')

            expect(postUrl?.href).toBe('https://maps.dwd.de/geoserver/wfs')
        })

        it('produces a document without any validation issue', () => {
            const document = {
                type: 'FeatureCollection',
                id: 'urn:uuid:0f8fad5b-d9cb-469f-a165-70867728950e',
                properties: {
                    lang: 'en',
                    title: 'mixed',
                    updated: '2026-10-23T00:00:00Z',
                    links: { profiles: ['http://www.opengis.net/spec/owc-geojson/1.0/req/core'] }
                },
                features: wfsToOWSResources(GET_CAPABILITIES_HREF, capabilities)
            }
            const result = validateOwsContext(JSON.parse(JSON.stringify(document)))

            expect(result.hasErrors).toBe(false)
            expect(result.issues).toEqual([])
        })
    })

    it('lets the types own OutputFormats replace the operation wide ones without merging', () => {
        const capabilities = parseWfs(mapServerCapabilities)
        const featureType = capabilities.featureTypes.find(type => type.name === 'ms:Countries')
        const feature = featuresByName(capabilities).get('ms:Countries')

        expect(feature?.getWfsOffering()?.outputFormats).toEqual(featureType?.outputFormats)
        expect(getFeatureUrl(feature)?.searchParams.get('OUTPUTFORMAT'))
            .toBe(negotiatedFeatureTypeFormats(featureType!, capabilities.operationUrls.getFeature)[0])
    })

    describe('with a minimal WFS without namespace, bounds, CRS or POST binding', () => {

        const capabilities = parseWfs(minimalCapabilities)
        const feature = featuresByName(capabilities).get('plain_type')

        it('stays silent about everything the service does not state', () => {
            const offering = feature?.getWfsOffering()

            expect(offering?.qualifiedName).toBe('plain_type')
            expect(offering?.namespace).toBeUndefined()
            expect(offering?.defaultCrs).toBeUndefined()
            expect(offering?.otherCrs).toEqual([])
            expect(feature?.bbox).toBeUndefined()
            expect(getFeatureUrl(feature)?.searchParams.has('SRSNAME')).toBe(false)
            expect(getFeatureUrl(feature)?.searchParams.get('OUTPUTFORMAT'))
                .toBe('application/gml+xml; version=3.2')
        })

        it('does not fabricate a POST operation for a service that advertises none', () => {
            expect(feature?.getWfsOperationByCode('GetFeature', 'POST')).toBeUndefined()
        })
    })

    it('keeps same local names from distinct namespaces as distinct resources', () => {
        const capabilities = parseWfs(prefixVariantCapabilities)
        const features = featuresByName(capabilities)
        const resources = wfsToOWSResources(GET_CAPABILITIES_HREF, capabilities)

        expect(resources.length).toBe(3)
        expect(features.get('alpha:parcels')?.getWfsOffering()?.namespace)
            .toBe('https://alpha.example.test/schema')
        expect(features.get('beta:parcels')?.getWfsOffering()?.namespace)
            .toBe('https://beta.example.test/schema')
        expect(getFeatureUrl(features.get('alpha:parcels'))?.searchParams.get('TYPENAME'))
            .toBe('alpha:parcels')
        // the service advertises DescribeFeatureType without a GET binding => no operation is built
        expect(resources[0].getWfsOperationByCode('DescribeFeatureType', 'GET')).toBeUndefined()
    })
})

describe('OWSContext.appendWfs', () => {

    const buildContext = () => {
        const context = new OWSContext()
        context.bbox = [0, 0, 10, 10]
        context.appendWfs('https://maps.dwd.de/geoserver/wfs?service=WFS&version=2.0.0', dwdCapabilities)
        return context
    }

    it('appends a new tree, keeps the viewport and tags the GetCapabilities URL with WFS', () => {
        const context = buildContext()
        const root = context.features[0]

        expect(root.properties.folder).toBe('/0')
        expect(context.bbox).toEqual([0, 0, 10, 10])
        const capabilitiesOperation = new URL(root.getWfsOperationByCode('GetCapabilities')!.href)
        // the given href already stated service and version in lowercase; the preparation keeps the
        // existing spellings and only adds the missing request parameter
        expect(capabilitiesOperation.searchParams.get('service')).toBe('WFS')
        expect(capabilitiesOperation.searchParams.get('REQUEST')).toBe('GetCapabilities')
        expect(capabilitiesOperation.searchParams.get('version')).toBe('2.0.0')
    })

    it('appends following services as further trees without touching the first one', () => {
        const context = buildContext()
        const firstTreeFolders = context.features.map(feature => feature.properties.folder)

        const treeId = context.appendWfs('https://maps.example.test/wfs', minimalCapabilities)
        const appended = context.features.slice(firstTreeFolders.length)

        expect(treeId).toBe(1)
        expect(appended[0].properties.folder).toBe('/1')
        expect(context.features.slice(0, firstTreeFolders.length)
            .map(feature => feature.properties.folder)).toEqual(firstTreeFolders)
        expect(context.bbox).toEqual([0, 0, 10, 10])
    })

    it('keeps a mixed WMS and WFS context through export and reimport', () => {
        const context = buildContext()
        context.appendWms('https://www.example.org/wms?request=getcapabilities',
            capabilitiesInherited)
        const wfsLeaf = context.features.find(feature =>
            feature.getWfsOffering()?.qualifiedName === 'dwd:RBSN_T2m')!
        context.activateFeature(wfsLeaf.properties.folder, true)

        const exported = validateOwsContext(JSON.parse(JSON.stringify(context)))
        expect(exported.hasErrors).toBe(false)
        expect(exported.issues).toEqual([])

        const restored = OWSContext.fromPlainObject(exported.context!)
        const restoredLeaf = restored.findResourceByFolder(wfsLeaf.properties.folder)

        expect(restored.features.length).toBe(context.features.length)
        expect(restored.bbox).toEqual(context.bbox)
        expect(restoredLeaf?.properties.active).toBe(true)
        expect(restoredLeaf?.bbox).toEqual(wfsLeaf.bbox)
        expect(restoredLeaf?.getWfsOperationByCode('GetFeature')?.href)
            .toBe(wfsLeaf.getWfsOperationByCode('GetFeature')?.href)
        expect(restored.features.filter(feature => feature.getWmsOffering() !== undefined).length)
            .toBe(context.features.filter(feature => feature.getWmsOffering() !== undefined).length)
    })

    it('normalizes legacy WFS offerings and keeps unsupported alternatives losslessly', () => {
        const properties = normalizeResourceProperties({
            title: 'mixed',
            updated: '2026-10-23T00:00:00Z',
            offerings: [
                {
                    code: 'http://www.opengis.net/spec/owc-atom/1.0/req/wfs',
                    operations: [
                        { code: 'GetFeature', method: 'GET', href: 'https://example.test/wfs' },
                        // an operation the viewer does not know stays untouched
                        { code: 'GetPropertyValue', method: 'GET', href: 'https://example.test/wfs' }
                    ]
                },
                // an offering the viewer cannot render stays as an extension
                { code: 'https://example.test/own-offering', title: 'kept' }
            ]
        })

        expect(properties.offerings?.[0].code).toBe(WFS_OFFERING_CODE)
        expect(properties.offerings?.[1].code).toBe('https://example.test/own-offering')
        expect(properties.offerings?.[1].title).toBe('kept')

        const result = validateOwsContext({
            type: 'FeatureCollection',
            id: 'urn:uuid:0f8fad5b-d9cb-469f-a165-70867728950e',
            properties: { lang: 'en', title: 'mixed', updated: '2026-10-23T00:00:00Z' },
            features: [{ type: 'Feature', properties }]
        })
        expect(result.hasErrors).toBe(false)
        // one warning for the unknown offering, one for the unknown operation; nothing is dropped
        expect(result.issues
            .filter(issue => issue.severity === 'warning' && issue.path.includes('offerings')).length)
            .toBe(2)
        expect(result.context?.features[0].properties.offerings?.[0].operations?.length).toBe(2)
    })
})

describe('WFS request descriptors are separate from the WMS activation', () => {

    const buildMixedContext = () => {
        const context = new OWSContext()
        context.appendWfs('https://example.test/wfs', minimalCapabilities)
        context.appendWfs('https://maps.dwd.de/geoserver/wfs', dwdCapabilities)
        context.activateFeature('/0/0', true)
        context.activateFeature('/1/0', true)
        return context
    }

    it('builds one descriptor per active feature type and never batches unrelated endpoints', () => {
        const context = buildMixedContext()
        const descriptors = context.getWfsFeatureRequests()

        expect(descriptors.length).toBe(2)
        const urls = descriptors.map(descriptor => new URL(descriptor.operation.href))
        expect(urls.map(url => url.origin + url.pathname).sort()).toEqual([
            'https://example.test/wfs',
            'https://maps.dwd.de/geoserver/wfs'
        ])
        expect(descriptors.every(descriptor => descriptor.feature.getWfsOffering() !== undefined)).toBe(true)
    })

    it('ignores inactive resources and group nodes stay without a descriptor of their own', () => {
        const context = buildMixedContext()
        context.activateFeature('/0/0', false)
        context.activateFeature('/1', false)

        expect(context.getWfsFeatureRequests().length).toBe(0)

        const groupOnly = new OWSContext()
        groupOnly.appendWfs('https://example.test/wfs', minimalCapabilities)
        groupOnly.activateFeature('/0', true)
        // activating the whole tree activates the group node too, which has no GetFeature operation
        expect(groupOnly.getWfsFeatureRequests().length).toBe(1)
    })

    it('leaves the WMS optimized URLs untouched for WFS features', () => {
        const context = buildMixedContext()

        expect(context.getOptimizedUrlsByCode('GetMap')).toEqual([])
    })
})