import { describe, expect, it } from 'vitest'

import { parseWms } from '../parseCapabilities'
import { AdvertisedDimension, WmsLayer } from '../types'
import dimensionsCapabilities from './capabilities_dimensions_130.xml?raw'

const childOf = (layer: WmsLayer, name: string): WmsLayer => {
    const found = layer.children?.find(child => child.metadata.name === name)
    if (found === undefined) throw new Error(`fixture has no child layer "${name}"`)
    return found
}

const byName = (dimensions: AdvertisedDimension[] | undefined, name: string) =>
    dimensions?.find(dimension => dimension.name === name)

describe('parseWms collecting advertised dimensions', () => {

    const capabilities = parseWms(dimensionsCapabilities)
    const root = capabilities.rootLayer

    it('keeps the name, units, default and raw value text of every stated dimension', () => {
        expect(root.advertisedDimension).toHaveLength(2)
        expect(byName(root.advertisedDimension, 'elevation')).toEqual({
            name: 'elevation', values: '0,10,20', units: 'CRS:84', unitSymbol: 'm', default: '10'
        })
        expect(byName(root.advertisedDimension, 'DIM_sensor')).toEqual({
            name: 'DIM_sensor', values: '0/100/10', units: 'C', default: '0'
        })
    })

    it('inherits every dimension a child does not state itself', () => {
        const inheriting = childOf(root, 'tests:inheriting')
        expect(inheriting.advertisedDimension).toEqual(root.advertisedDimension)
    })

    it('replaces the inherited dimension of the same name and keeps the others', () => {
        const overriding = childOf(root, 'tests:overriding')
        expect(byName(overriding.advertisedDimension, 'elevation')).toEqual(
            byName(root.advertisedDimension, 'elevation'))
        expect(byName(overriding.advertisedDimension, 'DIM_sensor')).toEqual({
            name: 'DIM_sensor', values: '5,15'
        })
    })
})
