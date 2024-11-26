import type { Polygon } from 'geojson'

import { Identifier, type RaRecord } from 'react-admin'

import { LatLng, LatLngBounds } from 'leaflet'

import { WMSTree, type TreeNode } from '../../react-ows-lib/ContextProvider/OwsContextBase'

export const deflatTree = (node: TreeNode): TreeNode[] => {
  const nodes = [node]
  if (node.children.length > 0){
    node.children.forEach(childNode => {
      nodes.push(...deflatTree(childNode))
    })
  }
  return nodes
}

export const findChildrenById = (tree: WMSTree, id: Identifier): TreeNode | undefined => {
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