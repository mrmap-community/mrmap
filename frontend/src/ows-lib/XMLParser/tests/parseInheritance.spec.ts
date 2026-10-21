import { describe, expect, it } from 'vitest'

import { parseWms } from '../parseCapabilities'
import { TimeDimension, WmsLayer } from '../types'
import inheritedCapabilities from './capabilities_inherited_130.xml?raw'
import latLonCapabilities from './capabilities_latlon_111.xml?raw'

/** the child a capabilities tree describes under a given layer name */
const childOf = (layer: WmsLayer, name: string): WmsLayer => {
    const found = layer.children?.find(child => child.metadata.name === name)
    if (found === undefined) throw new Error(`fixture has no child layer "${name}"`)
    return found
}

const styleNames = (layer: WmsLayer) => layer.styles?.map(style => style.metadata.name)

const timeDimensionStartYear = (layer: WmsLayer) =>
    new Date((layer.dimension?.[0] as TimeDimension).start).getUTCFullYear()

describe('parseWms resolving inherited layer settings', () => {

    const capabilities = parseWms(inheritedCapabilities)
    const root = capabilities.rootLayer

    it('parses the settings stated by the WMS 1.3.0 root layer', () => {
        expect(capabilities.version).toBe('1.3.0')
        expect(root.metadata.name).toBe('')
        expect(root.referenceSystems).toEqual(['EPSG:4326', 'EPSG:3857'])
        expect(root.bbox).toEqual([5, 45, 15, 55])
        expect(styleNames(root)).toEqual(['shared'])
        expect(root.isQueryable).toBe(true)
        expect(root.isOpaque).toBe(false)
        expect(root.isCascaded).toBe(true)
        expect(root.minScaleDenominator).toBe(1000)
        expect(root.maxScaleDenominator).toBe(100000)
    })

    it('inherits every setting a named child does not state itself', () => {
        const inheriting = childOf(root, 'tests:inheriting')

        expect(inheriting.bbox).toEqual([5, 45, 15, 55])
        expect(inheriting.referenceSystems).toEqual(['EPSG:4326', 'EPSG:3857'])
        expect(styleNames(inheriting)).toEqual(['shared'])
        expect(inheriting.minScaleDenominator).toBe(1000)
        expect(inheriting.maxScaleDenominator).toBe(100000)
        expect(inheriting.isQueryable).toBe(true)
        expect(timeDimensionStartYear(inheriting)).toBe(2020)
    })

    it('lets a child override inherited settings, including stated false and zero values', () => {
        const overriding = childOf(root, 'tests:overriding')

        expect(overriding.isQueryable).toBe(false)
        expect(overriding.isOpaque).toBe(true)
        expect(overriding.minScaleDenominator).toBe(0)
        expect(overriding.bbox).toEqual([6, 46, 7, 47])
        // what the child does not state stays inherited
        expect(overriding.isCascaded).toBe(true)
        expect(overriding.maxScaleDenominator).toBe(100000)
        // reference systems and styles of the child are added to the inherited ones
        expect(overriding.referenceSystems).toEqual(['EPSG:4326', 'EPSG:3857', 'EPSG:25832'])
        expect(styleNames(overriding)).toEqual(['shared', 'own'])
        expect(timeDimensionStartYear(overriding)).toBe(2024)
    })

    it('inherits over more than one level and replaces a repeated style by name', () => {
        const unnamedGroup = root.children?.[2]

        expect(unnamedGroup?.metadata.name).toBe('')

        const nested = childOf(unnamedGroup ?? root, 'tests:nested')
        expect(nested.bbox).toEqual([5, 45, 15, 55])
        expect(nested.minScaleDenominator).toBe(1000)
        expect(nested.styles).toHaveLength(1)
        expect(nested.styles?.[0].metadata.title).toBe('Nested shared style')
    })
})

describe('parseWms reading WMS 1.1.1 geographic extents', () => {

    const capabilities = parseWms(latLonCapabilities)
    const root = capabilities.rootLayer

    it('reads the extent of a LatLonBoundingBox element', () => {
        expect(capabilities.version).toBe('1.1.1')
        expect(root.bbox).toEqual([5, 40, 25, 50])
    })

    it('splits the reference systems of a whitespace separated SRS element', () => {
        expect(root.referenceSystems).toEqual(['EPSG:4326', 'EPSG:3857', 'EPSG:900913'])
    })

    it('inherits extent, reference systems, style and scale into the named child', () => {
        const inheriting = childOf(root, 'tests:inheriting')

        expect(inheriting.bbox).toEqual([5, 40, 25, 50])
        expect(inheriting.referenceSystems).toEqual(['EPSG:4326', 'EPSG:3857', 'EPSG:900913'])
        expect(styleNames(inheriting)).toEqual(['raster'])
        expect(inheriting.maxScaleDenominator).toBe(250000)
        expect(inheriting.isQueryable).toBe(true)
    })

    it('keeps the LatLonBoundingBox a child states itself', () => {
        expect(childOf(root, 'tests:own-extent').bbox).toEqual([6, 46, 7, 47])
    })

    it('describes no GetFeatureInfo operation the capabilities do not request', () => {
        expect(capabilities.operationUrls.getFeatureInfo).toBeUndefined()
    })
})
