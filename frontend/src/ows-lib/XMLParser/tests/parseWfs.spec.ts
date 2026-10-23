import { describe, expect, it } from 'vitest'

import { parseWfs } from '../parseWfs'
import { negotiatedFeatureTypeFormats } from '../types'
import dwdCapabilities from './wfs_2_0_0_dwd.xml?raw'
import mapserverCapabilities from './wfs_2_0_0_mapserver.xml?raw'
import minimalCapabilities from './wfs_minimal_2_0_0.xml?raw'
import prefixVariantCapabilities from './wfs_prefix_variant_2_0_0.xml?raw'

const EXCEPTION_CAPABILITIES = `<?xml version="1.0" encoding="UTF-8"?>
<ows:ExceptionReport version="2.0.0" xmlns:ows="http://www.opengis.net/ows/1.1">
  <ows:Exception exceptionCode="InvalidParameterValue" locator="TYPENAMES">
    <ows:ExceptionText>Unknown feature type</ows:ExceptionText>
  </ows:Exception>
</ows:ExceptionReport>`

const WMS_CAPABILITIES_STUB = `<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms"/>`

const UNSUPPORTED_VERSION_CAPABILITIES = `<?xml version="1.0" encoding="UTF-8"?>
<WFS_Capabilities version="1.1.0" xmlns="http://www.opengis.net/wfs/2.0"/>`

const NAMELESS_FEATURETYPE_CAPABILITIES = `<?xml version="1.0" encoding="UTF-8"?>
<WFS_Capabilities version="2.0.0" xmlns="http://www.opengis.net/wfs/2.0" xmlns:ows="http://www.opengis.net/ows/1.1">
  <ows:OperationsMetadata>
    <ows:Operation name="GetFeature">
      <ows:DCP><ows:HTTP><ows:Get xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="https://example.test/wfs"/></ows:HTTP></ows:DCP>
    </ows:Operation>
  </ows:OperationsMetadata>
  <FeatureTypeList><FeatureType><Title>nameless</Title></FeatureType></FeatureTypeList>
</WFS_Capabilities>`

describe('parseWfs of a real WFS 2.0.0 capabilities document', () => {

    const capabilities = parseWfs(dwdCapabilities)

    it('parses the service identification and version', () => {
        expect(capabilities.version).toBe('2.0.0')
        expect(capabilities.metadata.title).toBe('DWD GeoServer WFS')
        expect(capabilities.serviceType).toBe('WFS')
        expect(capabilities.serviceTypeVersions).toContain('2.0.0')
    })

    it('parses GetFeature bindings, operation-wide formats and result constraints', () => {
        const getFeature = capabilities.operationUrls.getFeature
        expect(getFeature.get).toBe('https://maps.dwd.de/geoserver/wfs')
        expect(getFeature.post).toBe('https://maps.dwd.de/geoserver/wfs')
        expect(getFeature.mimeTypes).toHaveLength(16)
        expect(getFeature.mimeTypes).toContain('application/json')
        expect(getFeature.parameters['resultType']).toEqual(['results', 'hits'])
        expect(getFeature.constraints['CountDefault']).toBe('2147483647')
        expect(getFeature.constraints['PagingIsTransactionSafe']).toBe('FALSE')
    })

    it('parses a qualified feature type with namespace, bounds, CRS and metadata', () => {
        const featureType = capabilities.featureTypes.find(type => type.name === 'dwd:RBSN_T2m')
        expect(featureType).toBeDefined()
        expect(featureType?.namespaceUri).toBe('http://www.dwd.de')
        expect(featureType?.metadata.title).toBe('2m Temperatur an RBSN Stationen')
        expect(featureType?.bounds).toEqual([6.02439799999999, 47.398578, 14.950565, 55.010987])
        expect(featureType?.defaultCrs).toBe('urn:ogc:def:crs:EPSG::4258')
        expect(featureType?.metadataUrl).toContain('registry.gdi-de.org')
    })

    it('falls back to the operation-wide formats for types stating none', () => {
        const featureType = capabilities.featureTypes.find(type => type.name === 'dwd:RBSN_T2m')
        expect(featureType?.outputFormats).toEqual([])
        expect(negotiatedFeatureTypeFormats(featureType!, capabilities.operationUrls.getFeature))
            .toEqual(capabilities.operationUrls.getFeature.mimeTypes)
    })

    it('keeps all advertised feature types', () => {
        expect(capabilities.featureTypes.length).toBeGreaterThan(10)
        expect(capabilities.featureTypes.every(type => type.name.includes(':'))).toBe(true)
    })
})

describe('parseWfs of a local MapServer WFS 2.0.0', () => {

    const capabilities = parseWfs(mapserverCapabilities)
    const getFeature = capabilities.operationUrls.getFeature

    it('parses the single feature type stated in the FeatureTypeList', () => {
        expect(capabilities.featureTypes).toHaveLength(1)
        const featureType = capabilities.featureTypes[0]
        expect(featureType.name).toBe('ms:Countries')
        expect(featureType.namespaceUri).toBe('http://mapserver.gis.umn.edu/mapserver')
        expect(featureType.bounds).toEqual([-180, -90, 180, 83.64513])
        expect(featureType.otherCrs).toEqual(['urn:ogc:def:crs:EPSG::25832', 'urn:ogc:def:crs:EPSG::25833'])
    })

    it('keeps the exactly advertised per-type output formats', () => {
        const featureType = capabilities.featureTypes[0]
        expect(featureType.outputFormats).toEqual([
            'application/gml+xml; version=3.2',
            'text/xml; subtype=gml/3.2.1',
            'text/xml; subtype=gml/3.1.1',
            'text/xml; subtype=gml/2.1.2'
        ])
        expect(negotiatedFeatureTypeFormats(featureType, getFeature)).toEqual(featureType.outputFormats)
    })

    it('parses bindings advertised directly on the Get and Post elements', () => {
        expect(getFeature.get).toContain('mapserv?map=/etc/mapserver/mapfiles/wfs_test_data.map&')
        expect(getFeature.post).toBe(getFeature.get)
        expect(capabilities.operationUrls.describeFeatureType).toBeDefined()
    })
})

describe('parseWfs of a minimal WFS 2.0.0', () => {

    const capabilities = parseWfs(minimalCapabilities)
    const getFeature = capabilities.operationUrls.getFeature

    it('does not imply optional answers', () => {
        expect(capabilities.metadata.title).toBe('Minimal WFS')
        expect(capabilities.operationUrls.describeFeatureType).toBeUndefined()
        expect(getFeature.post).toBeUndefined()
        expect(getFeature.constraints).toEqual({})
        expect(getFeature.parameters['resultType']).toBeUndefined()
    })

    it('parses an unprefixed feature type without optional fields', () => {
        const featureType = capabilities.featureTypes[0]
        expect(capabilities.featureTypes).toHaveLength(1)
        expect(featureType.name).toBe('plain_type')
        expect(featureType.namespaceUri).toBeUndefined()
        expect(featureType.bounds).toBeUndefined()
        expect(featureType.defaultCrs).toBeUndefined()
        expect(featureType.otherCrs).toEqual([])
        expect(featureType.outputFormats).toEqual([])
    })

    it('falls back to the operation-wide formats when the type states none', () => {
        expect(negotiatedFeatureTypeFormats(capabilities.featureTypes[0], getFeature))
            .toEqual(['application/gml+xml; version=3.2'])
    })
})

describe('parseWfs with different namespace prefixes', () => {

    const capabilities = parseWfs(prefixVariantCapabilities)
    const getFeature = capabilities.operationUrls.getFeature
    const [alpha, beta] = capabilities.featureTypes

    it('matches by localName instead of prefix spelling', () => {
        expect(capabilities.version).toBe('2.0.0')
        expect(getFeature.get).toBe('https://prefixed.example.test/wfs')
        expect(capabilities.serviceTypeVersions).toEqual(['2.0.0', '1.0.0'])
    })

    it('resolves same local names in distinct namespaces to their own URIs', () => {
        expect(capabilities.featureTypes.map(type => type.name)).toEqual(['alpha:parcels', 'beta:parcels'])
        expect(alpha.namespaceUri).toBe('https://alpha.example.test/schema')
        expect(beta.namespaceUri).toBe('https://beta.example.test/schema')
    })

    it('parses bounds crossing zero meridians and equator', () => {
        expect(alpha.bounds).toEqual([-1.5, -0.25, 2.75, 0.5])
        expect(alpha.otherCrs).toEqual(['urn:ogc:def:crs:EPSG::25832'])
    })

    it('keeps a post-only binding distinguishable', () => {
        const describe = capabilities.operationUrls.describeFeatureType
        expect(describe).toBeDefined()
        expect(describe?.get).toBe('')
        expect(describe?.post).toBe('https://prefixed.example.test/wfs')
    })

    it('answers constraints only where they carry a value', () => {
        expect(getFeature.constraints['ImplementsResultPaging']).toBe('TRUE')
        expect('PagingIsTransactionSafe' in getFeature.constraints).toBe(false)
        expect(capabilities.filterConstraints['ImplementsBasicFilters']).toBe('TRUE')
    })

    it('negotiates per-type formats over the operation-wide ones', () => {
        expect(negotiatedFeatureTypeFormats(alpha, getFeature))
            .toEqual(['application/gml+xml; version=3.2', 'application/json'])
        expect(negotiatedFeatureTypeFormats(beta, getFeature))
            .toEqual(['application/json', 'text/xml; subtype=gml/3.2'])
    })
})

describe('parseWfs rejecting what it cannot honestly answer', () => {

    it('reports an OGC exception report with code and text', () => {
        expect(() => parseWfs(EXCEPTION_CAPABILITIES))
            .toThrowError(/OGC exception InvalidParameterValue: Unknown feature type/)
    })

    it('names an unsupported WFS version instead of parsing it', () => {
        expect(() => parseWfs(UNSUPPORTED_VERSION_CAPABILITIES))
            .toThrowError(/Unsupported WFS version '1\.1\.0'/)
    })

    it('refuses a capabilities document of another protocol', () => {
        expect(() => parseWfs(WMS_CAPABILITIES_STUB)).toThrowError(/Not a WFS capabilities document/)
    })

    it('fails on malformed XML', () => {
        expect(() => parseWfs('<?xml version="1.0"?><WFS_Capabilities version="2.0.0">')).toThrowError(/Invalid XML document/)
    })

    it('refuses a feature type it cannot identify', () => {
        expect(() => parseWfs(NAMELESS_FEATURETYPE_CAPABILITIES))
            .toThrowError(/feature type without a Name/)
    })

    it('refuses a WFS without GetFeature', () => {
        expect(() => parseWfs(minimalCapabilities.replace('GetFeature', 'GetNothing')))
            .toThrowError(/without a GetFeature operation/)
    })
})
