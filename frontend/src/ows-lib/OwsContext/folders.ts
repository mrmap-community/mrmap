import { v4 as uuidv4 } from 'uuid'

import { OWSResource as IOWSResource } from './types'

/**
 * Normalization of the grouping an OWS Context document describes with the optional "folder" member.
 *
 * The standard (OGC 14-055r2, chapter 7.1.2.19) defines a folder as a hierarchical position inside
 * the context: a resource in "/root/algal" belongs to the group "algal" inside the group "root". It
 * does not define a naming scheme for the segments, it does not require every group to be described
 * by a resource of its own and it does not require the member at all. A document may therefore name
 * its groups, leave parents out, order its resources arbitrarily or group nothing at all.
 *
 * The layer tree of the viewer and every editing operation on it work on numbered, complete and gap
 * free paths ("/0", "/0/3", ...) as created by "updateFolders", so the grouping of a document is
 * normalized onto that internal representation before the viewer works with it:
 *
 * - the segments keep their order but lose their names, the numbering follows the document,
 * - a group without a resource of its own is replaced by a synthesized group resource which carries
 *   the name of the segment as title, so the described hierarchy stays visible,
 * - resources without a folder become root resources,
 * - the resources are returned ordered depth first, which keeps the drawing order of documents that
 *   are already ordered by their tree, and every resource of the document keeps its id.
 */

/** prefix of a grouping the document does not name, i.e. of a resource without a folder */
const ANONYMOUS_PREFIX = '\u0000'

export interface FolderGroupingIssue {
    /** path of the resource which caused the issue, e.g. "features[3].properties.folder" */
    path: string
    message: string
}

export interface FolderGrouping {
    /**
     * every resource of the document exactly once, holding a numbered folder, ordered depth first
     * and completed by the group resources the document does not describe
     */
    features: IOWSResource[]
    /** what the normalization had to change about the grouping of the document */
    issues: FolderGroupingIssue[]
}

interface FolderNode {
    key: string
    children: FolderNode[]
    /** the resource describing this folder, if the document describes one */
    resource?: IOWSResource
    /** index of that resource within the features array of the document */
    documentIndex?: number
    /** folder value of that resource, to report a renamed grouping */
    folder?: string
    /** numbered path assigned to this folder */
    path: string
}

/** the segments of a folder path, leading and trailing separators are no segments */
export const splitFolderPath = (folder: string): string[] =>
    folder.split('/').filter(segment => segment.length > 0)

const createNode = (key: string): FolderNode => ({ key: key, children: [], path: '' })

/**
 * Add a resource to the folder tree, creating the groups its path names on the way. A resource
 * without a folder becomes a root resource of its own, keyed by the position it has in the document.
 */
const addResource = (root: FolderNode, resource: IOWSResource, documentIndex: number) => {
    const folder = resource.properties?.folder
    const segments = typeof folder === 'string' ? splitFolderPath(folder) : []
    const keys = segments.length > 0 ? segments : [`${ANONYMOUS_PREFIX}${documentIndex}`]

    const node = keys.reduce((parent, key) => {
        const found = parent.children.find(child => child.key === key)
        if (found !== undefined) return found

        const created = createNode(key)
        parent.children.push(created)
        return created
    }, root)

    if (node.resource === undefined) {
        node.resource = resource
        node.documentIndex = documentIndex
        node.folder = folder
        return
    }

    // two resources claiming the same folder is reported as an error by the validation; keep both of
    // them visible by nesting the second one inside the first instead of dropping it
    node.children.push({ ...createNode(`${ANONYMOUS_PREFIX}${documentIndex}`), resource, documentIndex, folder })
}

/** number every folder of the tree, following the order the document gives its resources */
const numberFolders = (node: FolderNode): void => {
    node.children.forEach((child, index) => {
        child.path = `${node.path}/${index}`
        numberFolders(child)
    })
}

/** timestamp of the first resource below a node, so a group does not need to invent one */
const firstUpdated = (node: FolderNode): string | undefined => {
    const updated = node.resource?.properties?.updated
    if (typeof updated === 'string' && updated.length > 0) return updated
    return node.children.map(firstUpdated).find(childUpdated => childUpdated !== undefined)
}

/** the resource standing for a group the document only names but does not describe */
const groupResource = (node: FolderNode): IOWSResource => ({
    type: 'Feature',
    id: uuidv4(),
    properties: {
        title: node.key,
        updated: firstUpdated(node) ?? new Date().toISOString(),
        folder: node.path
    }
})

/** index of the first resource below a node, to report a group by the resource which names it */
const firstDocumentIndex = (node: FolderNode): number | undefined => {
    if (node.documentIndex !== undefined) return node.documentIndex
    return node.children.map(firstDocumentIndex).find(index => index !== undefined)
}

/**
 * Collect the resources of a node depth first, parents before their children, and report what the
 * normalization had to add or change on the way.
 */
const collectResources = (
    node: FolderNode,
    namedPath: string[],
    collected: IOWSResource[],
    issues: FolderGroupingIssue[],
): number => {
    let renamed = 0

    node.children.forEach((child) => {
        const childNamedPath = [...namedPath, child.key]

        if (child.resource === undefined) {
            collected.push(groupResource(child))
            const describedBy = firstDocumentIndex(child)
            if (describedBy !== undefined)
                issues.push({
                    path: `features[${describedBy}].properties.folder`,
                    message: `names the group "/${childNamedPath.join('/')}" which no resource of the document describes, a group resource has been created`
                })
        } else {
            collected.push({
                ...child.resource,
                properties: { ...child.resource.properties, folder: child.path }
            })
            // a resource without a folder was not named by the document, it is not renamed
            if (child.folder !== undefined && child.folder !== child.path) renamed++
        }

        renamed += collectResources(child, childNamedPath, collected, issues)
    })

    return renamed
}

/**
 * Normalize the grouping of the given resources onto the numbered folder structure the layer tree
 * works with. The given resources are not modified; every returned resource is a copy which keeps the
 * id of the resource it was created from.
 */
export const normalizeFolderPaths = (features: IOWSResource[]): FolderGrouping => {
    const root = createNode('')
    const issues: FolderGroupingIssue[] = []

    features.forEach((resource, index) => addResource(root, resource, index))
    numberFolders(root)

    const collected: IOWSResource[] = []
    const renamed = collectResources(root, [], collected, issues)

    if (renamed > 0)
        issues.push({
            path: 'features',
            message: `${renamed} ${renamed === 1 ? 'resource' : 'resources'} described another folder than the numbered one the viewer works with, the grouping of the document is preserved`
        })

    return { features: collected, issues: issues }
}

const compareFolderSegment = (segmentA: string, segmentB: string): number => {
    const numberA = Number(segmentA)
    const numberB = Number(segmentB)
    if (Number.isFinite(numberA) && Number.isFinite(numberB)) return numberA - numberB
    return segmentA < segmentB ? -1 : segmentA > segmentB ? 1 : 0
}

/**
 * Compare two folder paths the way the layer tree orders them: segment by segment, a parent before
 * its children. Segments which are not numbered are compared by their name, resources without a
 * folder keep their place.
 */
export const compareFolderPaths = (folderA?: string, folderB?: string): number => {
    if (folderA === undefined || folderB === undefined) return 0

    const segmentsA = splitFolderPath(folderA)
    const segmentsB = splitFolderPath(folderB)
    const sharedSegments = Math.min(segmentsA.length, segmentsB.length)

    for (let index = 0; index < sharedSegments; index++) {
        const comparison = compareFolderSegment(segmentsA[index], segmentsB[index])
        if (comparison !== 0) return comparison
    }

    return segmentsA.length - segmentsB.length
}
