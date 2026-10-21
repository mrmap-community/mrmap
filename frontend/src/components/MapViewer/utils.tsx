import type { Polygon } from 'geojson'

import { Identifier, type RaRecord } from 'react-admin'

import { LatLng, LatLngBounds, latLngBounds } from 'leaflet'

import { OWSResource as TreeNode } from '../../ows-lib/OwsContext/core'

export const deflatTree = (node: TreeNode): TreeNode[] => {
  const nodes = [node]
  if (node.children.length > 0){
    node.children.forEach(childNode => {
      nodes.push(...deflatTree(childNode))
    })
  }
  return nodes
}

export const findChildrenById = (tree: { rootNode?: TreeNode }, id: Identifier): TreeNode | undefined => {
  if (tree.rootNode !== undefined){
    const flatTree = deflatTree(tree.rootNode)
    return flatTree.find(node => node.id === id)
  }
}

export const collectChildren = (node: TreeNode, includeSelf: boolean = false): TreeNode[] => {
  const children = []

  if (includeSelf) {
    children.push(node)
  }
  children.push(...node.children)
  for (const child of children) {
    children.push(...collectChildren(child))
  }
  return children
}

export const getAnchestors = (nodes: RaRecord[], currentNode: RaRecord): RaRecord[] => {
  return nodes?.filter(
    node =>
      node?.mpttLft < currentNode?.mpttLft &&
            node?.mpttRgt > currentNode?.mpttRgt
  )
}

export const getDescendants = (nodes: RaRecord[], currentNode: RaRecord, includeSelf: boolean = false): RaRecord[] => {
  const descendants = nodes?.filter(
    node =>
      node?.mpttLft > currentNode?.mpttLft &&
            node?.mpttRgt < currentNode?.mpttRgt
  )
  return [
    ...(includeSelf ? [currentNode]: []),
    ...descendants,
  ]
}

export const getChildren = (nodes: RaRecord[], currentNode: RaRecord): RaRecord[] => {
  return getDescendants(nodes, currentNode).filter(
    node => node?.mpttDepth === currentNode?.mpttDepth as number + 1
  )
}

export const isDescendantOf = (nodeA: RaRecord, nodeB: RaRecord): boolean => {
  return (nodeA.mpttLft > nodeB.mpttLft && nodeA.mpttRgt < nodeB.mpttRgt)
}

export const isAncestorOf = (nodeA: RaRecord, nodeB: RaRecord): boolean => {
  return isDescendantOf(nodeB, nodeA)
}

/**
 * The area of interest of a viewer, in the longitude / latitude order of the `EPSG:4326` map it is
 * shown on and therefore in the same order as the bounding box of an OWS Context is stored.
 */
export type Extent = [west: number, south: number, east: number, north: number]

/**
 * Whether `extent` describes an area that a viewer can show: four finite numbers within the lon /
 * lat range of `EPSG:4326` that span more than a point. An extent that is missing, malformed or
 * collapsed to a point is not an area of interest and the viewer keeps the view it has.
 */
export const validExtent = (extent?: number[] | null): extent is Extent => Boolean(
  Array.isArray(extent) &&
  extent.length === 4 &&
  extent.every(Number.isFinite) &&
  -180 <= extent[0] &&
  extent[0] < extent[2] &&
  extent[2] <= 180 &&
  -90 <= extent[1] &&
  extent[1] < extent[3] &&
  extent[3] <= 90
)

/** The area of interest `extent` as the bounds leaflet wants them in, which is lat / lng. */
export const extentBounds = (extent: Extent) =>
  latLngBounds([extent[1], extent[0]], [extent[3], extent[2]])

/**
 * The area of interest the viewport `bounds` shows, clamped to the world of `EPSG:4326`: a view with
 * a soft boundary can reach over a pole and a view zoomed out can reach over its edges.
 */
export const boundsToExtent = (bounds: LatLngBounds): Extent => {
  const clamp = (value: number, min: number, max: number) =>
    Math.min(max, Math.max(min, value))
  return [
    clamp(bounds.getWest(), -180, 180),
    clamp(bounds.getSouth(), -90, 90),
    clamp(bounds.getEast(), -180, 180),
    clamp(bounds.getNorth(), -90, 90)
  ]
}

export const latLngToGeoJSON = (point: LatLng) => {
  if (point === undefined){
    return
  }
  return `
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [${point.lng}, ${point.lat}]
      },
      "properties": {
        "name": "viewer center"
      }
    }
  `
}

export const boundsToGeoJSON = (bounds: LatLngBounds) => {
  if (bounds === undefined){
    return
  }
  return `
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [${bounds.getSouthWest().lng}, ${bounds.getSouthWest().lat}], 
          [${bounds.getNorthEast().lng}, ${bounds.getSouthWest().lat}], 
          [${bounds.getNorthEast().lng}, ${bounds.getNorthEast().lat}], 
          [${bounds.getSouthWest().lng}, ${bounds.getNorthEast().lat}],
          [${bounds.getSouthWest().lng}, ${bounds.getSouthWest().lat}]
        ]]
      },
      "properties": {
        "name": "viewer bbox"
      }
    }
  `
}

export const featuresToCollection = (features: string[]) => {
  if (features === undefined){
    return
  }
  return `
  { 
    "type": "FeatureCollection",
    "features": [
      ${features.join(',')}
    ]
  }
`
}

export const polygonToFeature = (geojson: Polygon, name: string) => {
  if (geojson == undefined){
    return
  }
  return `
    {
      "type": "Feature",
      "geometry": ${geojson},
      "properties": {
        "name": "${name}"
      }
    }
  `
}