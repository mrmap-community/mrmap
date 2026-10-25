import { describe, expect, it } from 'vitest'

import wmsCapabilities from '../../XMLParser/tests/capabilitites_130.xml?raw'
import wfsCapabilities from '../../XMLParser/tests/wfs_2_0_0_dwd.xml?raw'
import { serializeOwsContext } from '../authentication'
import { OWSContext } from '../core'
import { detectCapabilitiesService } from '../utils'

const WMS_HREF = 'https://www.example.org/wms?SERVICE=WMS&REQUEST=GetCapabilities'
const WFS_HREF = 'https://www.example.org/wfs?SERVICE=WFS&REQUEST=GetCapabilities'

/** a document that carries a WMS tree and a WFS tree side by side, with one active member each */
const mixedContext = () => {
    const context = new OWSContext()
    context.appendWms(WMS_HREF, wmsCapabilities)
    context.appendWfs(WFS_HREF, wfsCapabilities)

    const wmsLeaf = context.features.find(feature =>
        feature.getWmsOperationByCode('GetMap') !== undefined)!
    wmsLeaf.getWmsOperationByCode('GetMap')!.active = true
    wmsLeaf.properties.active = true

    const wfsLeaf = context.features.find(feature =>
        feature.getWfsOperationByCode('GetFeature', 'GET') !== undefined)!
    wfsLeaf.properties.active = true

    context.bbox = [0, 40, 20, 60]
    return { context, wmsLeaf, wfsLeaf }
}

describe('a mixed WMS and WFS document', () => {
    it('reads each capabilities document its own protocol from', () => {
        expect(detectCapabilitiesService(wmsCapabilities)).toBe('WMS')
        expect(detectCapabilitiesService(wfsCapabilities)).toBe('WFS')
        expect(detectCapabilitiesService('<html><body>no service</body></html>')).toBeUndefined()
    })

    it('exports and reloads with the same selection, order, visibility and viewport', () => {
        const { context, wmsLeaf, wfsLeaf } = mixedContext()

        const reloaded = OWSContext.fromPlainObject(
            JSON.parse(serializeOwsContext(context)))

        // the same trees in the same order
        expect(reloaded.features.map(feature => feature.properties.folder))
            .toEqual(context.features.map(feature => feature.properties.folder))

        // the same selection: the WMS layer through its operation, the WFS type through itself
        const reloadedWms = reloaded.features.find(feature =>
            feature.properties.folder === wmsLeaf.properties.folder)!
        const reloadedWfs = reloaded.features.find(feature =>
            feature.properties.folder === wfsLeaf.properties.folder)!
        expect(reloadedWms.getWmsOperationByCode('GetMap')?.active).toBe(true)
        expect(reloadedWfs.properties.active).toBe(true)
        expect(reloaded.features.filter(feature => feature.properties.active === true))
            .toEqual(expect.arrayContaining([
                expect.objectContaining({
                    properties: expect.objectContaining({ title: wfsLeaf.properties.title }),
                }),
            ]))

        // the WFS request data the viewer builds its bounded requests from stays lossless
        const offering = reloadedWfs.getWfsOffering()!
        expect(offering.qualifiedName).toEqual(wfsLeaf.getWfsOffering()!.qualifiedName)
        expect(offering.outputFormats).toEqual(wfsLeaf.getWfsOffering()!.outputFormats)
        expect(offering.defaultCrs).toEqual(wfsLeaf.getWfsOffering()!.defaultCrs)
        expect(reloadedWfs.getWfsOperationByCode('GetFeature', 'GET')?.href)
            .toEqual(wfsLeaf.getWfsOperationByCode('GetFeature', 'GET')?.href)

        // the viewport of the document survives
        expect(reloaded.bbox).toEqual([0, 40, 20, 60])
    })

    it('keeps the two protocols apart after a reload: the WMS stays in the WMS batch, the WFS in its descriptors', () => {
        const { context } = mixedContext()
        const reloaded = OWSContext.fromPlainObject(
            JSON.parse(serializeOwsContext(context)))

        const wmsBatches = reloaded.getOptimizedUrlsByCode('GetMap',
            feature => feature.getWmsOperationByCode('GetMap')?.active === true)
        const wfsRequests = reloaded.getWfsFeatureRequests()

        expect(wmsBatches.length).toBeGreaterThan(0)
        expect(wmsBatches.every(batch => batch.features
            .every(feature => feature.getWmsOffering() !== undefined))).toBe(true)
        expect(wfsRequests.length).toBe(1)
        expect(wfsRequests[0].feature.getWfsOffering()).not.toBeUndefined()
        expect(wfsRequests[0].feature.getWmsOffering()).toBeUndefined()
    })
})
