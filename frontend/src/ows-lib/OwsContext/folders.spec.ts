import { describe, expect, it } from 'vitest'

import { compareFolderPaths, normalizeFolderPaths, splitFolderPath } from './folders'
import { OWSResource as IOWSResource } from './types'

const UPDATED = '2024-05-03T10:26:38.476Z'

const resource = (title: string, folder?: string, id?: string): IOWSResource => ({
    type: 'Feature',
    ...(id !== undefined && { id: id }),
    properties: {
        title: title,
        updated: UPDATED,
        ...(folder !== undefined && { folder: folder })
    }
})

const foldersOf = (resources: IOWSResource[]) => resources.map(resource => resource.properties.folder)

describe('splitFolderPath', () => {

    it('ignores leading and trailing separators', () => {
        expect(splitFolderPath('/root/algal/')).toEqual(['root', 'algal'])
        expect(splitFolderPath('/')).toEqual([])
        expect(splitFolderPath('')).toEqual([])
    })
})

describe('normalizeFolderPaths', () => {

    it('keeps a numbered, complete and gap free grouping untouched', () => {
        const resources = [
            resource('root', '/0', 'root-id'),
            resource('child', '/0/0', 'child-id'),
            resource('second', '/1', 'second-id')
        ]

        const grouping = normalizeFolderPaths(resources)

        expect(foldersOf(grouping.features)).toEqual(['/0', '/0/0', '/1'])
        expect(grouping.features.map(feature => feature.id)).toEqual(['root-id', 'child-id', 'second-id'])
        expect(grouping.issues).toEqual([])
        // the given resources are not modified
        expect(foldersOf(resources)).toEqual(['/0', '/0/0', '/1'])
    })

    it('does not need a grouping at all', () => {
        const grouping = normalizeFolderPaths([
            resource('first', undefined, 'first-id'),
            resource('second', undefined, 'second-id')
        ])

        expect(foldersOf(grouping.features)).toEqual(['/0', '/1'])
        expect(grouping.issues).toEqual([])
    })

    it('numbers a named grouping and keeps the described hierarchy', () => {
        const grouping = normalizeFolderPaths([
            resource('root', '/root', 'root-id'),
            resource('algal', '/root/algal', 'algal-id'),
            resource('water', '/water', 'water-id')
        ])

        expect(foldersOf(grouping.features)).toEqual(['/0', '/0/0', '/1'])
        expect(grouping.features.map(feature => feature.id)).toEqual(['root-id', 'algal-id', 'water-id'])
        expect(grouping.issues.map(issue => issue.path)).toEqual(['features'])
    })

    it('creates a group resource for the folder a document only names', () => {
        const grouping = normalizeFolderPaths([resource('algal', '/root/algal', 'algal-id')])

        expect(foldersOf(grouping.features)).toEqual(['/0', '/0/0'])
        expect(grouping.features[0].properties.title).toEqual('root')
        // the group takes over the timestamp of the resource below it instead of inventing one
        expect(grouping.features[0].properties.updated).toEqual(UPDATED)
        expect(grouping.features[1].id).toEqual('algal-id')
        expect(grouping.issues.map(issue => issue.path)).toEqual(['features[0].properties.folder', 'features'])
    })

    it('creates every group of a deeply nested path', () => {
        const grouping = normalizeFolderPaths([resource('leaf', '/a/b/c', 'leaf-id')])

        expect(foldersOf(grouping.features)).toEqual(['/0', '/0/0', '/0/0/0'])
        expect(grouping.features.map(feature => feature.properties.title)).toEqual(['a', 'b', 'leaf'])
        expect(grouping.issues.map(issue => issue.path)).toEqual([
            'features[0].properties.folder',
            'features[0].properties.folder',
            'features'
        ])
    })

    it('orders a parent in front of the children described before it', () => {
        const grouping = normalizeFolderPaths([
            resource('child', '/0/1', 'child-id'),
            resource('sibling', '/0/0', 'sibling-id'),
            resource('parent', '/0', 'parent-id')
        ])

        // the numbering follows the document, therefore the child described first keeps the first index
        expect(foldersOf(grouping.features)).toEqual(['/0', '/0/0', '/0/1'])
        expect(grouping.features.map(feature => feature.id)).toEqual(['parent-id', 'child-id', 'sibling-id'])
    })

    it('closes the gaps of a numbered grouping', () => {
        const grouping = normalizeFolderPaths([resource('first', '/0'), resource('second', '/7')])

        expect(foldersOf(grouping.features)).toEqual(['/0', '/1'])
        expect(grouping.issues.map(issue => issue.path)).toEqual(['features'])
    })

    it('keeps every resource of a document which describes a folder twice', () => {
        const grouping = normalizeFolderPaths([
            resource('first', '/0', 'first-id'),
            resource('copy', '/0', 'copy-id')
        ])

        expect(grouping.features.map(feature => feature.id)).toEqual(['first-id', 'copy-id'])
        expect(new Set(foldersOf(grouping.features)).size).toEqual(2)
    })

    it('passes the members of a resource which are no grouping through', () => {
        const grouping = normalizeFolderPaths([{
            type: 'Feature',
            id: 'algal-id',
            bbox: [0, 0, 1, 1],
            properties: { title: 'Algen', updated: UPDATED, folder: '/root/algal', active: true }
        }])

        const algal = grouping.features[1]
        expect(algal.bbox).toEqual([0, 0, 1, 1])
        expect(algal.properties.active).toBe(true)
    })
})

describe('compareFolderPaths', () => {

    it('orders parents before their children and siblings by their index', () => {
        expect(['/0/1', '/0', '/0/0', '/1'].sort(compareFolderPaths)).toEqual(['/0', '/0/0', '/0/1', '/1'])
    })

    it('orders segments which are not numbered by their name', () => {
        expect(['b', 'a'].sort(compareFolderPaths)).toEqual(['a', 'b'])
    })

    it('keeps resources without a folder in their place', () => {
        expect(compareFolderPaths(undefined, '/0')).toEqual(0)
        expect(compareFolderPaths('/0', undefined)).toEqual(0)
    })
})
