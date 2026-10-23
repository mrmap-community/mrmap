import { latLng, latLngBounds } from 'leaflet'
import { describe, expect, it } from 'vitest'

import { isWithinScaleLimits, metersPerPixel, scaleDenominatorForMap } from './scales'

const mapWith = (longitudeSpan: number, widthInPixels: number) => ({
    getBounds: () => latLngBounds([latLng(0, 0), latLng(1, longitudeSpan)]),
    getSize: () => ({ x: widthInPixels, y: widthInPixels }) as never,
})

describe('scale denominator of a view', () => {
    it('follows the 0.28 mm pixel convention of the WMS scale type', () => {
        // 4 degrees of longitude over 1000 px are ~445 m per px, i.e. a scale denominator of ~1.59e6
        expect(metersPerPixel(4, 1000)).toBeCloseTo(4 * (40075016.686 / 360) / 1000, 6)
        expect(scaleDenominatorForMap(mapWith(4, 1000) as never)).toBeCloseTo(1590278.44, 1)
    })

    it('grows when the view shows a wider area on the same pixels', () => {
        const near = scaleDenominatorForMap(mapWith(4, 1000) as never) as number
        const far = scaleDenominatorForMap(mapWith(8, 1000) as never) as number
        expect(far).toBeCloseTo(near * 2, 6)
    })

    it('stays unknown while the view cannot be measured', () => {
        expect(scaleDenominatorForMap(mapWith(0, 1000) as never)).toBeUndefined()
        expect(scaleDenominatorForMap(mapWith(4, 0) as never)).toBeUndefined()
    })
})

describe('scale limits of a layer', () => {
    it('renders a layer without stated limits at every scale', () => {
        expect(isWithinScaleLimits({}, 1)).toBe(true)
        expect(isWithinScaleLimits({}, 1_000_000)).toBe(true)
    })

    it('renders a layer while the scale of the view is unknown', () => {
        expect(isWithinScaleLimits({ minscaledenominator: 1000, maxscaledenominator: 50000 }, undefined)).toBe(true)
    })

    it('keeps both bounds of the interval in scale', () => {
        const limits = { minscaledenominator: 1000, maxscaledenominator: 50000 }
        expect(isWithinScaleLimits(limits, 1000)).toBe(true)
        expect(isWithinScaleLimits(limits, 50000)).toBe(true)
        expect(isWithinScaleLimits(limits, 25000)).toBe(true)
    })

    it('suppresses rendering below MinScaleDenominator and above MaxScaleDenominator', () => {
        const limits = { minscaledenominator: 1000, maxscaledenominator: 50000 }
        expect(isWithinScaleLimits(limits, 999.9)).toBe(false)
        expect(isWithinScaleLimits(limits, 50000.1)).toBe(false)
    })

    it('accepts one-sided limits', () => {
        expect(isWithinScaleLimits({ minscaledenominator: 1000 }, 2000)).toBe(true)
        expect(isWithinScaleLimits({ minscaledenominator: 1000 }, 500)).toBe(false)
        expect(isWithinScaleLimits({ maxscaledenominator: 50000 }, 60000)).toBe(false)
    })

    it('treats a zero lower bound and an infinite upper bound as no constraint', () => {
        expect(isWithinScaleLimits({ minscaledenominator: 0, maxscaledenominator: Number.POSITIVE_INFINITY }, 1_000_000)).toBe(true)
        expect(isWithinScaleLimits({ minscaledenominator: Number.POSITIVE_INFINITY }, 1_000_000)).toBe(false)
    })

    it('treats unusable limits as not stated, so the layer keeps rendering', () => {
        expect(isWithinScaleLimits({ minscaledenominator: -1 }, 100)).toBe(true)
        expect(isWithinScaleLimits({ maxscaledenominator: Number.NaN }, 100)).toBe(true)
        expect(isWithinScaleLimits({ minscaledenominator: 'wide' as never }, 100)).toBe(true)
    })
})
