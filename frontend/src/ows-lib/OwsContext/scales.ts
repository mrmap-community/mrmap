import type { Map } from 'leaflet'

/**
 * Scale limits of a WMS layer are stated as scale denominators and follow the OGC convention of a
 * 0.28 mm pixel (WMS 1.3.0, chapter 7.5.2.1, and OGC 06-012): a scale denominator is the ground
 * resolution in meters per pixel divided by 0.00028 m.
 *
 * The viewer navigates in geographic coordinates, so the ground resolution follows from the width
 * of the visible area in degrees, measured at the equator - the same reference the scale control of
 * the viewer uses. A layer shall not be rendered for a scale denominator smaller than its
 * MinScaleDenominator or larger than its MaxScaleDenominator; both bounds belong to the layer, so
 * equality stays in scale.
 */

/** the OGC pixel size of 0.28 mm the scale denominators of a WMS are measured in */
export const OGC_PIXEL_SIZE_IN_METERS = 0.00028

/** circumference of the earth in meters, the reference of the degrees to meters conversion */
export const EARTH_CIRCUMFERENCE_IN_METERS = 40075016.686

export interface ScaleLimits {
    minscaledenominator?: number
    maxscaledenominator?: number
}

/** the meters per pixel of a view which spans the given degrees of longitude over the given width */
export const metersPerPixel = (longitudeSpan: number, widthInPixels: number): number =>
    longitudeSpan * (EARTH_CIRCUMFERENCE_IN_METERS / 360) / widthInPixels

/**
 * The scale denominator of the current view of a map, or undefined while the map cannot answer
 * both its visible area and its size, e.g. before it has been laid out.
 */
export const scaleDenominatorForMap = (map: Map): number | undefined => {
    const bounds = map.getBounds()
    const size = map.getSize()
    const longitudeSpan = Math.abs(bounds.getEast() - bounds.getWest())
    if (!(longitudeSpan > 0) || !(size.x > 0)) {
        return undefined
    }
    return metersPerPixel(longitudeSpan, size.x) / OGC_PIXEL_SIZE_IN_METERS
}

/**
 * A stated limit is only trusted when it is a non negative number; the WMS scale type additionally
 * allows "infinity". Anything else - a negative value, NaN, a string which survived an older
 * document - is treated as not stated, so the layer keeps rendering instead of silently vanishing.
 */
const usableLimit = (limit: number | undefined): number | undefined =>
    typeof limit === 'number' && !Number.isNaN(limit) && limit >= 0 ? limit : undefined

/**
 * Whether a layer with the given scale limits shall be rendered at the given scale denominator.
 * A layer without usable limits is always in scale, and so is every layer while the scale of the
 * view is unknown: the viewer suppresses rendering only once it knows better.
 */
export const isWithinScaleLimits = (limits: ScaleLimits, scaleDenominator: number | undefined): boolean => {
    if (scaleDenominator === undefined || Number.isNaN(scaleDenominator)) {
        return true
    }
    const min = usableLimit(limits.minscaledenominator)
    const max = usableLimit(limits.maxscaledenominator)
    if (min !== undefined && scaleDenominator < min) return false
    if (max !== undefined && scaleDenominator > max) return false
    return true
}
