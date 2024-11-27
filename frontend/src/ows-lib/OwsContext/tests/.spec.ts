
import { describe } from 'node:test'
import { expect, test } from 'vitest'

import { WmsCapabilitites } from '../../XMLParser/types'
import { OWSResource } from '../core'
import { Position } from '../enums'
import { OWSResource as IOWSResource } from '../types'
import { treeify, updateFolders, wmsToOWSResources } from '../utils'
import { owsContextTest } from './test'

const getOwsResource = (title:string, folder: string, id?: number): OWSResource => {
    return new OWSResource({
        title: title,
        updated: '',
        folder: folder,
        
    },id)
}


test('wmsToOWSContext', () => {
    const capabilities: WmsCapabilitites = {
        version: '1.3.0',
        metadata: {
            name: "test wms",
            title: "test wms title"
        },
        operationUrls: {
            getCapabilities: {
                mimeTypes: ['application/xml'],
                get: 'http://example.com/?SERVICE=wms&REQUEST=GetCapabilities'
            },
            getMap: {
                mimeTypes: ['image/png'],
                get: 'http://example.com/?SERVICE=wms&REQUEST=GetMap'
            },
        },
        rootLayer: {
            metadata: {
                name: 'node 1',
                title: 'node 1',
            },
            referenceSystems: ["EPSG:4326"],
            children: [
                {
                    metadata: {
                        name: 'node 1.1',
                        title: 'node 1.1'
                    },
                    children: [
                        {
                            metadata: {
                                name: 'node 1.1.1',
                                title: 'node 1.1.1'
                            }
                        },
                        {
                            metadata: {
                                name: 'node 1.1.2',
                                title: 'node 1.1.2'
                            }
                        },
                    ]
                },
                {
                    metadata: {
                        name: 'node 1.2',
                        title: 'node 1.2'
                    }
                },
            ]
        }
    }
    
    const features = wmsToOWSResources('http://example.com/?SERVICE=wms&REQUEST=GetCapabilities',capabilities)

    expect(features).toBeDefined()
    expect(features.length).equals(5)
})

owsContextTest('treeify success', ({karteRp}) => {
    const tree = treeify(karteRp.features)

    expect(tree.length).equals(1)
    expect(tree[0].children.length).equals(19)
    expect(tree[0].children[0].children.length).equals(4)
    expect(tree[0].children[1].children.length).equals(5)
    expect(tree[0].children[1].children[0].children.length).equals(0)
    expect(tree[0].children[18].children.length).equals(2)
})

owsContextTest('treeify wrong feature order', ({karteRp}) => {
    karteRp.features = karteRp.features.splice(2, 1)   
    
    expect(() => treeify(karteRp.features)).toThrowError('parsingerror... the context is not well ordered.')
})

owsContextTest('isDescandantOf', ({karteRp}) => {
    expect(karteRp.features[3].isDescendantOf(karteRp.features[0])).toBeTruthy()
    expect(karteRp.features[1].isDescendantOf(karteRp.features[0])).toBeTruthy()

    expect(karteRp.features[3].isDescendantOf(karteRp.features[3])).toBeFalsy()
    expect(karteRp.features[4].isDescendantOf(karteRp.features[3])).toBeFalsy()
    expect(karteRp.features[3].isDescendantOf(karteRp.features[4])).toBeFalsy()
    expect(karteRp.features[0].isDescendantOf(karteRp.features[4])).toBeFalsy()
    expect(karteRp.features[2].isDescendantOf(karteRp.features[4])).toBeFalsy()
})

owsContextTest('isAncestorOf', ({karteRp}) => {
    expect(karteRp.features[0].isAncestorOf(karteRp.features[3])).toBeTruthy()
    expect(karteRp.features[1].isAncestorOf(karteRp.features[3])).toBeTruthy()

    expect(karteRp.features[4].isAncestorOf(karteRp.features[3])).toBeFalsy()
    expect(karteRp.features[3].isAncestorOf(karteRp.features[0])).toBeFalsy()
    expect(karteRp.features[0].isAncestorOf(karteRp.features[0])).toBeFalsy()
})

owsContextTest('isChildOf', ({karteRp}) => {
    expect(karteRp.features[1].isChildOf(karteRp.features[0])).toBeTruthy()
    expect(karteRp.features[0].isChildOf(karteRp.features[1])).toBeFalsy()
    expect(karteRp.features[3].isChildOf(karteRp.features[0])).toBeFalsy()
})

owsContextTest('getParentFolder', ({karteRp}) => {
    expect(karteRp.features[0].getParentFolder()).toBeUndefined()
    expect(karteRp.features[1].getParentFolder()).equals('/0')
    expect(karteRp.features[3].getParentFolder()).equals('/0/0')
})

owsContextTest('isParentOf', ({karteRp}) => {
    expect(karteRp.features[0].isParentOf(karteRp.features[1])).toBeTruthy()
    expect(karteRp.features[1].isParentOf(karteRp.features[3])).toBeTruthy()

    expect(karteRp.features[1].isParentOf(karteRp.features[0])).toBeFalsy()
    expect(karteRp.features[3].isParentOf(karteRp.features[0])).toBeFalsy()
})

owsContextTest('getParentOf', ({karteRp}) => {
    expect(karteRp.getParentOf(karteRp.features[1])).equals(karteRp.features[0])
    expect(karteRp.getParentOf(karteRp.features[7])).equals(karteRp.features[6])
    expect(karteRp.getParentOf(karteRp.features[0])).toBeUndefined()
})

owsContextTest('isSiblingOf', ({karteRp}) => {
    expect(karteRp.features[1].isSiblingOf(karteRp.features[6])).toBeTruthy()
    expect(karteRp.features[2].isSiblingOf(karteRp.features[4])).toBeTruthy()
    
    expect(karteRp.features[0].isSiblingOf(karteRp.features[0])).toBeFalsy()
    expect(karteRp.features[0].isSiblingOf(karteRp.features[3])).toBeFalsy()
})

owsContextTest('getSiblingsOf', ({reducedKarteRp}) => {
    expect(reducedKarteRp.getSiblingsOf(reducedKarteRp.features[1])).toMatchObject([
        reducedKarteRp.features[6], 
        reducedKarteRp.features[12],
        reducedKarteRp.features[18],
        reducedKarteRp.features[27]])
    expect(reducedKarteRp.getSiblingsOf(reducedKarteRp.features[1],true)).toMatchObject([
        reducedKarteRp.features[1], 
        reducedKarteRp.features[6], 
        reducedKarteRp.features[12],
        reducedKarteRp.features[18],
        reducedKarteRp.features[27]])
    expect(reducedKarteRp.getSiblingsOf(reducedKarteRp.features[1], false, true)).toMatchObject([
        reducedKarteRp.features[6],
        reducedKarteRp.features[7],
        reducedKarteRp.features[8],
        reducedKarteRp.features[9],
        reducedKarteRp.features[10], 
        reducedKarteRp.features[11],
        reducedKarteRp.features[12],
        reducedKarteRp.features[13],
        reducedKarteRp.features[14],
        reducedKarteRp.features[15],
        reducedKarteRp.features[16],
        reducedKarteRp.features[17],
        reducedKarteRp.features[18],
        reducedKarteRp.features[19],
        reducedKarteRp.features[20],
        reducedKarteRp.features[21],
        reducedKarteRp.features[22],
        reducedKarteRp.features[23],
        reducedKarteRp.features[24],
        reducedKarteRp.features[25],
        reducedKarteRp.features[26],
        reducedKarteRp.features[27]])
    expect(reducedKarteRp.getSiblingsOf(reducedKarteRp.features[1], true, true)).toMatchObject([
        reducedKarteRp.features[1],
        reducedKarteRp.features[2],
        reducedKarteRp.features[3],
        reducedKarteRp.features[4],    
        reducedKarteRp.features[5], 
        reducedKarteRp.features[6],
        reducedKarteRp.features[7],
        reducedKarteRp.features[8],
        reducedKarteRp.features[9],
        reducedKarteRp.features[10], 
        reducedKarteRp.features[11],
        reducedKarteRp.features[12],
        reducedKarteRp.features[13],
        reducedKarteRp.features[14],
        reducedKarteRp.features[15],
        reducedKarteRp.features[16],
        reducedKarteRp.features[17],
        reducedKarteRp.features[18],
        reducedKarteRp.features[19],
        reducedKarteRp.features[20],
        reducedKarteRp.features[21],
        reducedKarteRp.features[22],
        reducedKarteRp.features[23],
        reducedKarteRp.features[24],
        reducedKarteRp.features[25],
        reducedKarteRp.features[26],
        reducedKarteRp.features[27]])

})

owsContextTest('getRightSiblings of Autobahnen', ({karteRp}) => {
    expect(karteRp.getRightSiblingsOf(karteRp.features[89], false, false)).toMatchObject(
        [
            karteRp.features[94], 
            karteRp.features[99], 
            karteRp.features[112]
        ]
    )
    expect(karteRp.getRightSiblingsOf(karteRp.features[89], true, false)).toMatchObject(
        [
            karteRp.features[89], 
            karteRp.features[94], 
            karteRp.features[99], 
            karteRp.features[112]
        ]
    )
    expect(karteRp.getRightSiblingsOf(karteRp.features[89], false, true)).toMatchObject(
        [
            karteRp.features[94],
            karteRp.features[95],
            karteRp.features[96],
            karteRp.features[97], 
            karteRp.features[98],
            karteRp.features[99], 
            karteRp.features[100],
            karteRp.features[101],
            karteRp.features[102],
            karteRp.features[103],
            karteRp.features[104],
            karteRp.features[105],
            karteRp.features[106],
            karteRp.features[107],
            karteRp.features[108],
            karteRp.features[109],
            karteRp.features[110],
            karteRp.features[111],
            karteRp.features[112],
            karteRp.features[113],
            karteRp.features[114],
        ]
    )
    expect(karteRp.getRightSiblingsOf(karteRp.features[89], true, true)).toMatchObject(
        [
            karteRp.features[89],
            karteRp.features[90],
            karteRp.features[91],
            karteRp.features[92],
            karteRp.features[93],
            karteRp.features[94],
            karteRp.features[95],
            karteRp.features[96],
            karteRp.features[97], 
            karteRp.features[98],
            karteRp.features[99], 
            karteRp.features[100],
            karteRp.features[101],
            karteRp.features[102],
            karteRp.features[103],
            karteRp.features[104],
            karteRp.features[105],
            karteRp.features[106],
            karteRp.features[107],
            karteRp.features[108],
            karteRp.features[109],
            karteRp.features[110],
            karteRp.features[111],
            karteRp.features[112],
            karteRp.features[113],
            karteRp.features[114],
        ]
    )
})

owsContextTest('getRightSiblings of wald 0', ({karteRp}) => {
    expect(karteRp.getRightSiblingsOf(karteRp.features[7], false, true)).toMatchObject([karteRp.features[8],karteRp.features[9],karteRp.features[10],karteRp.features[11]])
    expect(karteRp.getRightSiblingsOf(karteRp.features[7], true, true)).toMatchObject([karteRp.features[7],karteRp.features[8],karteRp.features[9],karteRp.features[10],karteRp.features[11]])
})

owsContextTest('getRightSiblings of wald 2', ({karteRp}) => {
    expect(karteRp.getRightSiblingsOf(karteRp.features[9], false, true)).toMatchObject([karteRp.features[10],karteRp.features[11]])
    expect(karteRp.getRightSiblingsOf(karteRp.features[9], true, true)).toMatchObject([karteRp.features[9],karteRp.features[10],karteRp.features[11]])
})

owsContextTest('getDescendants', ({karteRp}) => {
    expect(karteRp.getDescandantsOf(karteRp.features[1])).toMatchObject([karteRp.features[2], karteRp.features[3], karteRp.features[4], karteRp.features[5]])
    expect(karteRp.getDescandantsOf(karteRp.features[1], true)).toMatchObject([karteRp.features[1], karteRp.features[2], karteRp.features[3], karteRp.features[4], karteRp.features[5]])

    expect(karteRp.getDescandantsOf(karteRp.features[3])).toMatchObject([])
    expect(karteRp.getDescandantsOf(karteRp.features[3], true)).toMatchObject([karteRp.features[3]])
})

owsContextTest('getFirstChildIndexOf', ({karteRp}) => {
    expect(karteRp.getFirstChildIndexOf(karteRp.features[0])).equals(1)
    expect(karteRp.getFirstChildIndexOf(karteRp.features[2])).equals(-1)
})

owsContextTest('getLastChildFoderIndex', ({karteRp}) => {
    expect(karteRp.getLastChildFoderIndex(karteRp.features[0])).equals(18)
    expect(karteRp.getLastChildFoderIndex(karteRp.features[2])).equals(-1)
    expect(karteRp.getLastChildFoderIndex(karteRp.features[6])).equals(4)
})

owsContextTest('sortByFolder', ({karteRp}) => {
    const featuresCopy = JSON.parse(JSON.stringify(karteRp.features))

    karteRp.features = karteRp.features.toReversed()

    const feature1 = karteRp.features[1]
    const feature3 = karteRp.features[3]

    karteRp.features[1] = feature3
    karteRp.features[3] = feature1

    expect(karteRp.sortFeaturesByFolder()).toMatchObject(featuresCopy)
})

owsContextTest('moveFeature Land 0 as lastChild of Karte RP', ({karteRp}) => {
    const features = karteRp.moveFeature(karteRp.features[2], karteRp.features[0])
    
    expect(features?.[0].properties.folder).equals('/0')
    expect(features?.[0].properties.title).equals('Karte RP')

    expect(features?.[1].properties.folder).equals('/0/0')
    expect(features?.[1].properties.title).equals('Landesfläche')

    expect(features?.[2].properties.folder).equals('/0/0/0')
    expect(features?.[2].properties.title).equals('Land 1')

    expect(features?.[114].properties.folder).equals('/0/19')
    expect(features?.[114].properties.title).equals('Land 0')

})

owsContextTest('moveFeature Land 0 as firstChild of Karte RP', ({karteRp}) => {
    const features = karteRp.moveFeature(karteRp.features[2], karteRp.features[0], Position.firstChild)

    expect(features?.[0].properties.folder).equals('/0')
    expect(features?.[0].properties.title).equals('Karte RP')

    expect(features?.[1].properties.folder).equals('/0/0')
    expect(features?.[1].properties.title).equals('Land 0')

    expect(features?.[2].properties.folder).equals('/0/1')
    expect(features?.[2].properties.title).equals('Landesfläche')

    expect(features?.[3].properties.folder).equals('/0/1/0')
    expect(features?.[3].properties.title).equals('Land 1')

    expect(features?.[4].properties.folder).equals('/0/1/1')
    expect(features?.[4].properties.title).equals('Land 2')

    expect(features?.[5].properties.folder).equals('/0/1/2')
    expect(features?.[5].properties.title).equals('Land 3')
})


owsContextTest('moveFeature Land 0 left of Karte RP', ({karteRp}) => {
    const features = karteRp.moveFeature(karteRp.features[2], karteRp.features[0], Position.left)
    
    expect(features?.[0].properties.folder).equals('/0')
    expect(features?.[0].properties.title).equals('Land 0')

    expect(features?.[1].properties.folder).equals('/1')
    expect(features?.[1].properties.title).equals('Karte RP')

    expect(features?.[2].properties.folder).equals('/1/0')
    expect(features?.[2].properties.title).equals('Landesfläche')

    expect(features?.[3].properties.folder).equals('/1/0/0')
    expect(features?.[3].properties.title).equals('Land 1')

    expect(features?.[4].properties.folder).equals('/1/0/1')
    expect(features?.[4].properties.title).equals('Land 2')
})

owsContextTest('moveFeature Land 0 right of Karte RP', ({karteRp}) => {
    const features = karteRp.moveFeature(karteRp.features[2], karteRp.features[0], Position.right)
    
    expect(features?.[0].properties.folder).equals('/0')
    expect(features?.[0].properties.title).equals('Karte RP')

    expect(features?.[1].properties.folder).equals('/0/0')
    expect(features?.[1].properties.title).equals('Landesfläche')

    expect(features?.[2].properties.folder).equals('/0/0/0')
    expect(features?.[2].properties.title).equals('Land 1')

    expect(features?.[3].properties.folder).equals('/0/0/1')
    expect(features?.[3].properties.title).equals('Land 2')

    expect(features?.[4].properties.folder).equals('/0/0/2')
    expect(features?.[4].properties.title).equals('Land 3')

    expect(features?.[114].properties.folder).equals('/1')
    expect(features?.[114].properties.title).equals('Land 0')
})


owsContextTest('moveFeature wald3 as left sibling of wald0', ({karteRp}) => {

    const features = karteRp.moveFeature(karteRp.features[10], karteRp.features[7], Position.left)

    expect(features?.[7].properties.title).equals('Wald 3')
    expect(features?.[7].properties.folder).equals('/0/1/0')

    expect(features?.[8].properties.title).equals('Wald 0')
    expect(features?.[8].properties.folder).equals('/0/1/1')

})

owsContextTest('moveFeature wald3 as right sibling of wald0', ({karteRp}) => {

    // Wald 3 right of Wald 0
    const features = karteRp.moveFeature(karteRp.features[10], karteRp.features[7], Position.right)
    expect(features?.[7].properties.title).equals('Wald 0')
    expect(features?.[7].properties.folder).equals('/0/1/0')

    expect(features?.[8].properties.title).equals('Wald 3')
    expect(features?.[8].properties.folder).equals('/0/1/1')

    expect(features?.[9].properties.title).equals('Wald 1')
    expect(features?.[9].properties.folder).equals('/0/1/2')

    expect(features?.[10].properties.title).equals('Wald 2')
    expect(features?.[10].properties.folder).equals('/0/1/3')

    expect(features?.[11].properties.title).equals('Wald 4')
    expect(features?.[11].properties.folder).equals('/0/1/4')

})


owsContextTest('moveFeature wald3 as right sibling of wald2', ({karteRp}) => {

    // Wald 3 right of Wald 2
    const features = karteRp.moveFeature(karteRp.features[10], karteRp.features[9], Position.right)
    expect(features?.[7].properties.title).equals('Wald 0')
    expect(features?.[7].properties.folder).equals('/0/1/0')

    expect(features?.[8].properties.title).equals('Wald 1')
    expect(features?.[8].properties.folder).equals('/0/1/1')

    expect(features?.[9].properties.title).equals('Wald 2')
    expect(features?.[9].properties.folder).equals('/0/1/2')

    expect(features?.[10].properties.title).equals('Wald 3')
    expect(features?.[10].properties.folder).equals('/0/1/3')

    expect(features?.[11].properties.title).equals('Wald 4')
    expect(features?.[11].properties.folder).equals('/0/1/4')
})


owsContextTest('moveFeature wald3 as first child of wald2', ({karteRp}) => {

    // Wald 3 as first child of Wald 2
    const features = karteRp.moveFeature(karteRp.features[10], karteRp.features[9], Position.firstChild)

    expect(features?.[7].properties.title).equals('Wald 0')
    expect(features?.[7].properties.folder).equals('/0/1/0')

    expect(features?.[8].properties.title).equals('Wald 1')
    expect(features?.[8].properties.folder).equals('/0/1/1')

    expect(features?.[9].properties.title).equals('Wald 2')
    expect(features?.[9].properties.folder).equals('/0/1/2')

    expect(features?.[10].properties.title).equals('Wald 3')
    expect(features?.[10].properties.folder).equals('/0/1/2/0')

    expect(features?.[11].properties.title).equals('Wald 4')
    expect(features?.[11].properties.folder).equals('/0/1/3')
})
describe('move', ()=>{
    owsContextTest('moveFeature wald3 as left sibling of wald', ({karteRp}) => {
        // Wald 3 left of Wald
        const features = karteRp.moveFeature(karteRp.features[10], karteRp.features[6], Position.left)
       
        expect(features?.[6].properties.title).equals('Wald 3')
        expect(features?.[6].properties.folder).equals('/0/1')
    
        expect(features?.[7].properties.title).equals('Wald')
        expect(features?.[7].properties.folder).equals('/0/2')
    
        expect(features?.[8].properties.title).equals('Wald 0')
        expect(features?.[8].properties.folder).equals('/0/2/0')
    
        expect(features?.[9].properties.title).equals('Wald 1')
        expect(features?.[9].properties.folder).equals('/0/2/1')
    
        expect(features?.[10].properties.title).equals('Wald 2')
        expect(features?.[10].properties.folder).equals('/0/2/2')
    
        expect(features?.[11].properties.title).equals('Wald 4')
        expect(features?.[11].properties.folder).equals('/0/2/3')
    })
    
    
    owsContextTest('moveFeature sequence', ({karteRp}) => {

        // Wald 3 left of Wald
        const features = karteRp.moveFeature(karteRp.features[10], karteRp.features[6], Position.left)

        expect(features?.[6].properties.title).equals('Wald 3')
        expect(features?.[6].properties.folder).equals('/0/1')
    
        expect(features?.[7].properties.title).equals('Wald')
        expect(features?.[7].properties.folder).equals('/0/2')
    
        expect(features?.[8].properties.title).equals('Wald 0')
        expect(features?.[8].properties.folder).equals('/0/2/0')
    
        expect(features?.[9].properties.title).equals('Wald 1')
        expect(features?.[9].properties.folder).equals('/0/2/1')
    
        expect(features?.[10].properties.title).equals('Wald 2')
        expect(features?.[10].properties.folder).equals('/0/2/2')
    
        expect(features?.[11].properties.title).equals('Wald 4')
        expect(features?.[11].properties.folder).equals('/0/2/3')
    
        // Wald 2 left of Wald 3
        karteRp.moveFeature(karteRp.features[10], karteRp.features[6], Position.left)
    
        expect(features?.[6].properties.title).equals('Wald 2')
        expect(features?.[6].properties.folder).equals('/0/1')
    
        expect(features?.[7].properties.title).equals('Wald 3')
        expect(features?.[7].properties.folder).equals('/0/2')
    
        expect(features?.[8].properties.title).equals('Wald')
        expect(features?.[8].properties.folder).equals('/0/3')
    
        expect(features?.[9].properties.title).equals('Wald 0')
        expect(features?.[9].properties.folder).equals('/0/3/0')
    
        expect(features?.[10].properties.title).equals('Wald 1')
        expect(features?.[10].properties.folder).equals('/0/3/1')
    
        expect(features?.[11].properties.title).equals('Wald 4')
        expect(features?.[11].properties.folder).equals('/0/3/2')
    })
    
    
    owsContextTest('isLeafNode', ({karteRp}) => {
        expect(karteRp.isLeafNode(karteRp.features[0])).toBeFalsy()
        expect(karteRp.isLeafNode(karteRp.features[1])).toBeFalsy()
        
        expect(karteRp.isLeafNode(karteRp.features[2])).toBeTruthy()
        expect(karteRp.isLeafNode(karteRp.features[3])).toBeTruthy()
        expect(karteRp.isLeafNode(karteRp.features[4])).toBeTruthy()
    })
})


owsContextTest('validateFolderStructure', ({ karteRp }) => {   
   expect(karteRp.validateFolderStructure()).toBeTruthy()
})


test('updateFoders without start index', () => {
    const resources: OWSResource[] = [
        getOwsResource('/1', '/1', 1),
        getOwsResource('/1/2', '/1/2', 2),
        getOwsResource('/1/2/0', '/1/2/0', 3),
        getOwsResource('/1/2/3', '/1/2/3', 4),
    ]

    const expected: OWSResource[] = [
        getOwsResource('/1', '/0/0/0', 1),
        getOwsResource('/1/2', '/0/0/0/0', 2),
        getOwsResource('/1/2/0', '/0/0/0/0/0', 3),
        getOwsResource('/1/2/3', '/0/0/0/0/1', 4),

    ]

    updateFolders(resources, '/0/0', )

    expect(JSON.stringify(resources)).toEqual(JSON.stringify(expected))

})


test('updateFoders with start index', () => {
    const resources: OWSResource[] = [
        getOwsResource('/1', '/1', 1),
        getOwsResource('/1/2', '/1/2', 2),
        getOwsResource('/1/2/0', '/1/2/0', 3),
        getOwsResource('/1/2/3', '/1/2/3', 4),
    ]

    const expected: OWSResource[] = [
        getOwsResource('/1', '/0/0/2', 1),
        getOwsResource('/1/2', '/0/0/2/0', 2),
        getOwsResource('/1/2/0', '/0/0/2/0/0', 3),
        getOwsResource('/1/2/3', '/0/0/2/0/1', 4),
    ]

    updateFolders(resources, '/0/0', 2)

    expect(JSON.stringify(resources)).toEqual(JSON.stringify(expected))

})

test('updateFolders without new folderpath without start index', () => {
    const resources: OWSResource[] = [
        getOwsResource('/1', '/1', 1),
        getOwsResource('/1/2', '/1/2', 2),
        getOwsResource('/1/2/0', '/1/2/0', 3),
        getOwsResource('/1/2/3', '/1/2/3', 4),

    ]

    const expected: OWSResource[] = [
        getOwsResource('/1', '/0', 1),
        getOwsResource('/1/2', '/0/0', 2),
        getOwsResource('/1/2/0', '/0/0/0', 3),
        getOwsResource('/1/2/3', '/0/0/1',4 ),
    ]

    updateFolders(resources, '', )

    expect(JSON.stringify(resources)).toEqual(JSON.stringify(expected))

})

test('updateFoders with new path without start index', () => {
    const resources = [
        getOwsResource('/1', '/1', 1),
        getOwsResource('/1/2', '/1/2', 2),
        getOwsResource('/1/2/0', '/1/2/0', 3),
        getOwsResource('/1/2/3', '/1/2/3',4 ),
        getOwsResource('/1/3', '/1/4', 5),
    ]

    const expected = [
        getOwsResource('/1', '/2/4/0', 1),
        getOwsResource('/1/2', '/2/4/0/0', 2),
        getOwsResource('/1/2/0', '/2/4/0/0/0', 3),
        getOwsResource('/1/2/3', '/2/4/0/0/1',4 ),
        getOwsResource('/1/3', '/2/4/0/1', 5),
    ]

    updateFolders(resources, '/2/4', )

    expect(JSON.stringify(resources)).toEqual(JSON.stringify(expected))
})


owsContextTest('remove feature', ({karteRp}) => {
    // remove wald
    karteRp.removeFeature(karteRp.features[6])

    expect(karteRp.features[5].properties.title).equals('Land 3')
    expect(karteRp.features[5].properties.folder).equals('/0/0/3')

    expect(karteRp.features[6].properties.title).equals('Sonderkultur')
    expect(karteRp.features[6].properties.folder).equals('/0/1')

    expect(karteRp.features[7].properties.title).equals('Sonderkultur 0')
    expect(karteRp.features[7].properties.folder).equals('/0/1/0')

})


owsContextTest('insert feature as first child of Wald', ({karteRp}) => {
    const newFeature: IOWSResource = 
    {
        type: 'Feature',
        properties: {
            title: 'new node',
            updated: new Date().toString()
        }

    }
    karteRp.insertFeature(karteRp.features[6], newFeature, Position.firstChild)

    expect(karteRp.features[6].properties.title).equals('Wald')
    expect(karteRp.features[6].properties.folder).equals('/0/1')

    expect(karteRp.features[7].properties.title).equals('new node')
    expect(karteRp.features[7].properties.folder).equals('/0/1/0')

    expect(karteRp.features[8].properties.title).equals('Wald 0')
    expect(karteRp.features[8].properties.folder).equals('/0/1/1')
})

owsContextTest('insert feature as last child of Wald', ({karteRp}) => {
    const newFeature: IOWSResource = 
    {
        type: 'Feature',
        properties: {
            title: 'new node',
            updated: new Date().toString()
        }
    }
    
   karteRp.insertFeature(karteRp.features[6], newFeature, Position.lastChild)

   expect(karteRp.features[6].properties.title).equals('Wald')
   expect(karteRp.features[6].properties.folder).equals('/0/1')

   expect(karteRp.features[7].properties.title).equals('Wald 0')
   expect(karteRp.features[7].properties.folder).equals('/0/1/0')

   expect(karteRp.features[8].properties.title).equals('Wald 1')
   expect(karteRp.features[8].properties.folder).equals('/0/1/1')

   expect(karteRp.features[9].properties.title).equals('Wald 2')
   expect(karteRp.features[9].properties.folder).equals('/0/1/2')

   expect(karteRp.features[10].properties.title).equals('Wald 3')
   expect(karteRp.features[10].properties.folder).equals('/0/1/3')

   expect(karteRp.features[11].properties.title).equals('Wald 4')
   expect(karteRp.features[11].properties.folder).equals('/0/1/4')

   expect(karteRp.features[12].properties.title).equals('new node')
   expect(karteRp.features[12].properties.folder).equals('/0/1/5')
})

owsContextTest('insert feature left of Wald', ({karteRp}) => {
   const newFeature: IOWSResource = 
   {
       type: 'Feature',
       properties: {
           title: 'new node',
           updated: new Date().toString()
       }

   }
   karteRp.insertFeature(karteRp.features[6], newFeature, Position.left)

   expect(karteRp.features[6].properties.title).equals('new node')
   expect(karteRp.features[6].properties.folder).equals('/0/1')

   expect(karteRp.features[7].properties.title).equals('Wald')
   expect(karteRp.features[7].properties.folder).equals('/0/2')

   expect(karteRp.features[8].properties.title).equals('Wald 0')
   expect(karteRp.features[8].properties.folder).equals('/0/2/0')

   expect(karteRp.features[9].properties.title).equals('Wald 1')
   expect(karteRp.features[9].properties.folder).equals('/0/2/1')

   expect(karteRp.features[10].properties.title).equals('Wald 2')
   expect(karteRp.features[10].properties.folder).equals('/0/2/2')

   expect(karteRp.features[11].properties.title).equals('Wald 3')
   expect(karteRp.features[11].properties.folder).equals('/0/2/3')

   expect(karteRp.features[12].properties.title).equals('Wald 4')
   expect(karteRp.features[12].properties.folder).equals('/0/2/4')


})

owsContextTest('insert feature right of Wald', ({karteRp}) => {
   const newFeature: IOWSResource = 
   {
       type: 'Feature',
       properties: {
           title: 'new node',
           updated: new Date().toString()
       }

   }
   karteRp.insertFeature(karteRp.features[6], newFeature, Position.right)

   expect(karteRp.features[6].properties.title).equals('Wald')
   expect(karteRp.features[6].properties.folder).equals('/0/1')

   expect(karteRp.features[7].properties.title).equals('Wald 0')
   expect(karteRp.features[7].properties.folder).equals('/0/1/0')

   expect(karteRp.features[8].properties.title).equals('Wald 1')
   expect(karteRp.features[8].properties.folder).equals('/0/1/1')

   expect(karteRp.features[9].properties.title).equals('Wald 2')
   expect(karteRp.features[9].properties.folder).equals('/0/1/2')

   expect(karteRp.features[10].properties.title).equals('Wald 3')
   expect(karteRp.features[10].properties.folder).equals('/0/1/3')

   expect(karteRp.features[11].properties.title).equals('Wald 4')
   expect(karteRp.features[11].properties.folder).equals('/0/1/4')

   expect(karteRp.features[12].properties.title).equals('new node')
   expect(karteRp.features[12].properties.folder).equals('/0/2')

   expect(karteRp.features[13].properties.title).equals('Sonderkultur')
   expect(karteRp.features[13].properties.folder).equals('/0/3')
})