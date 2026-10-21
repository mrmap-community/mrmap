import { describe, expect, it } from 'vitest'

import { parseWms } from '../../XMLParser/parseCapabilities'
import inheritedCapabilities from '../../XMLParser/tests/capabilities_inherited_130.xml?raw'
import latLonCapabilities from '../../XMLParser/tests/capabilities_latlon_111.xml?raw'
import { WmsCapabilitites } from '../../XMLParser/types'
import { OWSResource } from '../core'
import { wmsToOWSResources } from '../utils'

const GET_CAPABILITIES_HREF = 'https://www.example.org/wms?SERVICE=WMS&REQUEST=GetCapabilities'

/** all resources of the imported capabilities, indexed by their title */
const featuresByTitle = (capabilities: WmsCapabilitites) =>
    new Map<string, OWSResource>(wmsToOWSResources(GET_CAPABILITIES_HREF, capabilities)
        .map(feature => [feature.properties.title, feature]))

const queryParam = (feature: OWSResource | undefined, code: string, parameter: string) => {
    const href = feature?.getWmsOperationByCode(code)?.href
    return href === undefined ? undefined : new URL(href).searchParams.get(parameter)
}

describe('wmsToOWSResources', () => {

    describe('with inherited WMS 1.3.0 layer settings', () => {

        const features = featuresByTitle(parseWms(inheritedCapabilities))

        it('carries the inherited extent, styles and scale hints over to the named child', () => {
            const inheriting = features.get('Inheriting layer')

            expect(inheriting?.bbox).toEqual([5, 45, 15, 55])
            expect(inheriting?.properties.minscaledenominator).toBe(1000)
            expect(inheriting?.properties.maxscaledenominator).toBe(100000)
            expect(inheriting?.getWmsOffering()?.styles).toEqual([{
                name: 'shared',
                title: 'Shared style',
                legendURL: 'https://www.example.org/legend/shared.png'
            }])
        })

        it('describes the queryability inherited by a child as a GetFeatureInfo operation', () => {
            expect(queryParam(features.get('Inheriting layer'), 'GetFeatureInfo', 'QUERY_LAYERS'))
                .toBe('tests:inheriting')
            // the child states queryable="0" and is not queryable, even though its parent is
            expect(features.get('Overriding layer')?.getWmsOperationByCode('GetFeatureInfo')).toBeUndefined()
        })

        it('honours the values a child states itself', () => {
            const overriding = features.get('Overriding layer')

            expect(queryParam(overriding, 'GetMap', 'LAYERS')).toBe('tests:overriding')
            expect(overriding?.bbox).toEqual([6, 46, 7, 47])
            expect(overriding?.properties.minscaledenominator).toBe(0)
            expect(overriding?.properties.maxscaledenominator).toBe(100000)
            expect(overriding?.getWmsOffering()?.styles?.map(style => style.name)).toEqual(['shared', 'own'])
        })

        it('does not describe a renderable GetMap operation for unnamed grouping layers', () => {
            const groupingLayer = features.get('Unnamed group')

            expect(groupingLayer?.getWmsOperationByCode('GetMap')).toBeUndefined()
            expect(groupingLayer?.getWmsOperationByCode('GetCapabilities')?.href).toBe(GET_CAPABILITIES_HREF)
            // the named children of the group stay renderable
            expect(queryParam(features.get('Nested layer'), 'GetMap', 'LAYERS')).toBe('tests:nested')
        })
    })

    describe('with WMS 1.1.1 geographic extents', () => {

        const features = featuresByTitle(parseWms(latLonCapabilities))

        it('describes the extent inherited from a LatLonBoundingBox', () => {
            const inheriting = features.get('Inheriting layer')

            expect(inheriting?.bbox).toEqual([5, 40, 25, 50])
            expect(queryParam(inheriting, 'GetMap', 'LAYERS')).toBe('tests:inheriting')
            expect(inheriting?.getWmsOffering()?.styles?.map(style => style.name)).toEqual(['raster'])
        })

        it('describes the extent a layer states itself', () => {
            expect(features.get('Layer with its own extent')?.bbox).toEqual([6, 46, 7, 47])
        })
    })
})
