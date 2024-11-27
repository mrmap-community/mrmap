import { BBox, Geometry } from 'geojson';

import { parseWms } from '../XMLParser/parseCapabilities';
import { Capabilites, WmsCapabilitites } from '../XMLParser/types';
import { Position } from './enums';
import { OWSContext as IOWSContext, OWSResource as IOWSResource, OWSContextProperties, OWSResourceProperties } from './types';
import { collectInheritedLayerProperties, getFeatureFolderIndex, isDescendant, prepareGetCapabilititesUrl, updateFolders, wmsToOWSResources } from './utils';


const VALID_PATH = new RegExp('(\/\d*)+')


export class OWSResource implements IOWSResource {
  properties: OWSResourceProperties;
  geometry?: Geometry;
  type: 'Feature';
  id?: string | number;
  bbox?: BBox;

  constructor(
    properties: OWSResourceProperties,
    id: string | number = Date.now().toString(),
    bbox: BBox | undefined = undefined,
    geometry: Geometry | undefined = undefined
  ) {
    this.properties = JSON.parse(JSON.stringify(properties))
    this.id = id
    this.bbox = bbox ? JSON.parse(JSON.stringify(bbox)) : undefined
    this.type = 'Feature'
    this.geometry = geometry ? JSON.parse(JSON.stringify(geometry)) : undefined
  }

  static fromPlainObject(resource: IOWSResource) {
    return new OWSResource(resource.properties, resource.id, resource.bbox, resource.geometry)
  }

  getWmsOffering() {
    return this.properties.offerings?.find(offering => offering.code === "http://www.opengis.net/spec/owc/1.0/req/wms")
  }

  getWmsGetMapOperation() {
    const wmsOffering = this.getWmsOffering()
    if (wmsOffering !== undefined) {
      return wmsOffering.operations?.find(operation => operation.code === "GetMap")
    }
  }

  getWmsGetCapabilitiesOperation() {
    const wmsOffering = this.getWmsOffering()
    if (wmsOffering !== undefined) {
      return wmsOffering.operations?.find(operation => operation.code === "GetCapabilities")
    }
  }

  getFolderIndex() {
    return getFeatureFolderIndex(this)
  }

  getParentFolder = () => {
    if (this.properties.folder?.split('/').length === 2) return // root node
    return this.properties.folder?.split('/').slice(0, -1).join('/')
  }

  isParentOf(child: OWSResource) {
    return this.properties.folder !== undefined &&
      child.properties.folder !== undefined &&
      this.isAncestorOf(child) &&
      this.properties.folder?.split('/').length === child.properties.folder?.split('/').length - 1
  }

  isDescendantOf(ancestor: OWSResource) {
    return isDescendant(ancestor, this)
  }

  isAncestorOf(descendant: OWSResource) {
    return isDescendant(this, descendant)
  }

  isChildOf(parent: OWSResource) {
    return parent.properties.folder !== undefined &&
      this.properties.folder !== undefined &&
      this.isDescendantOf(parent) &&
      this.properties.folder?.split('/').length === parent.properties.folder?.split('/').length + 1
  }

  isSiblingOf(sibling: OWSResource) {
    return this.properties.folder !== undefined &&
      sibling.properties.folder !== undefined &&
      this.properties.folder.split('/').length >= 2 &&
      sibling.properties.folder.split('/').length >= 2 &&
      this.getParentFolder() === sibling.getParentFolder() &&
      this !== sibling
  }
}


export class OWSContext implements IOWSContext {
  id: string;
  properties: OWSContextProperties;
  bbox?: BBox;
  date?: string;
  features: OWSResource[];
  type: 'FeatureCollection';

  capabilititesMap: { [url: string]: { capabilitites: Capabilites, features: OWSResource[] } };
  crsIntersection: string[]; // extension to calculate the reference systems which all active features supports

  constructor(
    id: string = Date.now().toString(),
    features: OWSResource[] = [],
    bbox: BBox = [-180, -90, 180, 90],
    properties: OWSContextProperties = {
      lang: 'en',
      title: 'mrmap ows context',
      updated: new Date().toISOString()
    },
    capabilititesMap = {}
  ) {
    this.id = id;
    this.type = "FeatureCollection";
    this.features = features;
    this.bbox = bbox;
    this.properties = JSON.parse(JSON.stringify(properties));

    this.capabilititesMap = capabilititesMap
    this.crsIntersection = []
  }
  [name: string]: unknown;

  async initialize() {
    await this.collectWmsCapabilities()

  }

  appendWms(href: string, capabilitites: string): this {
    const parsedWms = parseWms(capabilitites)

    const url = prepareGetCapabilititesUrl(href, 'WMS')

    const additionalFeatures = wmsToOWSResources(url.href, parsedWms, this.getNextRootId()).map(resource => new OWSResource(resource.properties))
    this.features.push(...additionalFeatures)

    if (url.href in this.capabilititesMap) {
      this.capabilititesMap[url.href].features = [...this.capabilititesMap[url.href].features, ...additionalFeatures]
    } else {
      this.capabilititesMap[url.href] = { capabilitites: parsedWms, features: additionalFeatures }
    }

    return this
  }

  appendWfs(capabilities: string): this {
    throw new Error('Method not implemented.');
  }

  findResourceByFolder(folder: string) {
    return this.features.find(feature => feature.properties.folder === folder)
  }

  getNextRootId(): number {
    let nextRootId = 0
    this.features.filter(feature => feature.properties.folder && feature.properties.folder.split('/').length === 2).forEach(rootNode => {
      const rootFolder = parseInt(rootNode.properties.folder?.split('/')[1] ?? '-1')
      if (rootFolder === nextRootId) {
        nextRootId = rootFolder + 1
      }
    })
    return nextRootId
  }

  moveFeature(source: OWSResource, target: OWSResource, position: Position = Position.lastChild): OWSResource[] {
    if (target.properties.folder === undefined ||
      source.properties.folder === undefined ||
      source === target
    ) return this.features

    this.validateFolderStructure()

    // first of all, get the objects before manipulating data. 
    // All filter functions will retun subsets with shallow copys
    const currentSourceSubtree = this.getDescandantsOf(source, true)
    const currentSourceSiblings = this.getSiblingsOf(source, false, false)
    const currentSourceSiblingtrees = this.getSiblingsOf(source, false, true)

    const currentSourceParentFolder = source.getParentFolder() ?? '/'
    const currentSourceFolders = currentSourceSubtree.map(node => node.properties.folder).filter(folder => folder !== undefined)

    const futureSiblings = this.getDescandantsOf(target, false).filter(descendant => !currentSourceFolders.includes(descendant.properties.folder))

    const currentTargetRightSiblingsIncludeSelf = this.getRightSiblingsOf(target, true, true).filter(feature => !currentSourceSubtree.includes(feature))
    const currentTargetRightSiblings = this.getRightSiblingsOf(target, false, true).filter(feature => {
      return !currentSourceSubtree.includes(feature)
    })

    if (position === Position.left) {
      const targetIndex = target.getFolderIndex()
      const newStartIndex = targetIndex || 0

      // move source subtrees to target position
      updateFolders(currentSourceSubtree, target.getParentFolder() ?? '', newStartIndex)

      // shift all right siblings of target one to the right (make some space for source tree to insert it)
      const nextRightStartIndex = currentTargetRightSiblingsIncludeSelf[0] !== undefined ? currentTargetRightSiblingsIncludeSelf[0].getFolderIndex() + 1 : this.getLastChildFoderIndex(target) + 1
      if (nextRightStartIndex === undefined) return this.features
      updateFolders(currentTargetRightSiblingsIncludeSelf, target.getParentFolder() ?? '', nextRightStartIndex)

    } else if (position === Position.right) {
      const targetIndex = target.getFolderIndex()
      const newStartIndex = targetIndex ? targetIndex + 1 : 1

      if (currentTargetRightSiblings[0] && currentTargetRightSiblings[0].getFolderIndex() - 1 === newStartIndex) return this.features // same position... nothing to do here

      // shift all right siblings of target one to the right (make some space for source tree to insert it)
      const nextRightStartIndex = currentTargetRightSiblings[0] !== undefined ? currentTargetRightSiblings[0].getFolderIndex() + 1 : this.getLastChildFoderIndex(target) + 1
      if (nextRightStartIndex === undefined) return this.features
      updateFolders(currentTargetRightSiblings, target.getParentFolder() ?? '', nextRightStartIndex)

      // shift source siblings one to the left (only needed if the source is removed as sibling)
      if (!source.isSiblingOf(target)) {
        updateFolders(currentSourceSiblingtrees, currentSourceParentFolder,)
      }

      // move source tree to new position
      updateFolders(currentSourceSubtree, target.getParentFolder() ?? '', newStartIndex)

    } else if (position === Position.lastChild) {
      // shift siblings to setup an ascending folder structure without spaces
      updateFolders(currentSourceSiblings, currentSourceParentFolder)
      // move source subtree to target position
      const lastChildFolderName = this.getLastChildFoderIndex(target)
      const relativPosition = Number(lastChildFolderName) + 1
      updateFolders(currentSourceSubtree, target.properties.folder, relativPosition)

    } else if (position === Position.firstChild) {

      if (currentSourceParentFolder !== target.properties.folder) {
        // shift all current source siblings to generate gap free ascendant index structure
        // only needed if current source parent is not the same 
        updateFolders(currentSourceSiblings, currentSourceParentFolder,)
      }

      // move source subtree to target position
      updateFolders(currentSourceSubtree, target.properties.folder, 0)
      // shift all siblings subtrees behind the first child
      updateFolders(futureSiblings, target.properties.folder, 1)

    }

    this.sortFeaturesByFolder()
    this.validateFolderStructure()
    return this.features
  }

  insertFeature(target: OWSResource, newResource: IOWSResource, position: Position = Position.lastChild) {

    const resource = new OWSResource(newResource.properties, newResource.id, newResource.bbox)

    if (position === Position.left) {
      resource.properties.folder = target.properties.folder
      const targetIndex = this.features.indexOf(target)

      const rightSubtrees = this.getRightSiblingsOf(target, true, true)
      const currentTargetNodeFolderIndex = target.getFolderIndex()
      const currentParentFolder = target.getParentFolder()

      updateFolders(rightSubtrees, currentParentFolder, currentTargetNodeFolderIndex + 1)

      // insert before target
      this.features.splice(targetIndex, 0, resource)


    } else if (position === Position.right) {

      const lastChild = this.getLastChildOf(target)
      if (lastChild === undefined) return
      const lastChildIndex = this.features.indexOf(lastChild)
      const rightSubtrees = this.getRightSiblingsOf(target, false, true)
      const currentParentFolder = target.getParentFolder()
      const currentTargetNodeFolderIndex = target.getFolderIndex()

      // setup as right sibling
      resource.properties.folder = `${target.getParentFolder()}/${currentTargetNodeFolderIndex + 1}`

      // move all right siblings of target one step right
      updateFolders(rightSubtrees, currentParentFolder, currentTargetNodeFolderIndex + 2)

      // insert after target
      this.features.splice(lastChildIndex + 1, 0, resource)

    } else if (position === Position.firstChild) {
      const targetIndex = this.features.indexOf(target)
      const targetDescendants = this.getDescandantsOf(target)
      const targetFolder = target.properties.folder

      resource.properties.folder = `${targetFolder}/0`
      // insert after target
      this.features.splice(targetIndex + 1, 0, resource)

      // move all siblings of the new feature one step right
      updateFolders(targetDescendants, targetFolder, 1)

    } else if (position === Position.lastChild) {
      const currentLastChild = this.getLastChildOf(target)
      if (currentLastChild === undefined) return

      const currentLastChildIndex = this.features.indexOf(currentLastChild)
      const currentLastChildNodeFolderIndex = currentLastChild.getFolderIndex()

      resource.properties.folder = `${currentLastChild.getParentFolder()}/${currentLastChildNodeFolderIndex + 1}`

      // insert after currentLastChild
      this.features.splice(currentLastChildIndex + 1, 0, resource)
    }
    this.sortFeaturesByFolder()
    this.validateFolderStructure()
  }

  sortFeaturesByFolder() {
    this.features.sort((a, b) => {
      const pathA = a.properties.folder?.split('/').map(Number);
      const pathB = b.properties.folder?.split('/').map(Number);
      if (pathA === undefined || pathB === undefined) return -1

      for (let i = 0; i < Math.min(pathA.length, pathB.length); i++) {
        if (pathA[i] !== pathB[i]) {
          return pathA[i] - pathB[i];
        }
      }
      return pathA.length - pathB.length;
    });
    return this.features
  }

  getIndeterminateStateOf(target: OWSResource) {
    if (this.properties.active === true) return false
    const descendants = this.getDescandantsOf(target)
    return descendants.length > 0 && descendants.find(feature => feature.properties.active === true) !== undefined
  }

  isLeafNode(target: OWSResource) {
    const anyChild = this.features.find(node => node.properties.folder !== this.properties.folder && isDescendant(target, node))
    return anyChild === undefined
  }

  getLeafNodes() {
    return this.features.filter(feature => this.isLeafNode(feature))
  }

  validateFolderStructure(): boolean {
    let previousFeature: OWSResource

    this.features.forEach((feature, index) => {
      if (feature === undefined) throw new Error(`feature with index ${index} was undefined`)
      const folder = feature.properties.folder
      if (folder === undefined || folder === '') throw new Error(`feature ${index} has an undefined folder`)
      if (!VALID_PATH.test(folder)) throw new Error(`folder of feature ${index} value does not match the regex: ${folder}`)

      if (index === 0) {
        if (folder !== '/0') throw new Error(`first feature must be /0. It was: ${folder}`)
        previousFeature = feature
        return
      }

      if (feature.isChildOf(previousFeature)) {
        if (feature.getFolderIndex() !== 0) throw new Error(`first child must always start with index 0. It was ${feature.getFolderIndex()}; Path: ${folder}, previous ${previousFeature.properties.folder}; loop idx: ${index}`)
        previousFeature = feature
        return
      }

      if (feature.isSiblingOf(previousFeature)) {
        if (previousFeature.getFolderIndex() + 1 !== feature.getFolderIndex()) throw new Error(`index of following siblings must be increase strict by 1. Index: ${index}; Folder: ${folder}, prevFolder: ${previousFeature.properties.folder}`)
        previousFeature = feature
        return
      }

      // last but not least, it can only be the next sibling of any parent
      const parentFolder = previousFeature.getParentFolder()
      const pathParts = parentFolder?.split('/').filter(part => part !== '');

      let siblingFound = false

      // Iteriere über die Teile des Pfads
      for (let i = pathParts?.length ?? 0; i > 0; i--) {
        const partialPath = '/' + pathParts?.slice(0, i).join('/')
        const parentResource = this.findResourceByFolder(partialPath)
        if (parentResource && feature.isSiblingOf(parentResource)) {
          siblingFound = true
          break
        }
      }

      if (!siblingFound) {
        throw new Error(`feature with index ${index} has no previous sibling.`)
      }
      previousFeature = feature
    })

    return true
  }

  getParentOf(target: OWSResource) {
    if (target.properties.folder === undefined) return
    const parentFolderName = target.getParentFolder()
    if (parentFolderName === undefined || parentFolderName === '/') return
    return this.features.find(feature => feature.properties.folder === parentFolderName)
  }

  getAncestorsOf(target: OWSResource, include_self: boolean = false) {
    const ancestors = this.features.filter(feature => target.isDescendantOf(feature))
    if (include_self) return [...ancestors, this]
    return ancestors
  }

  getDescandantsOf(target: OWSResource, includeSelf: boolean = false) {
    const descendants = this.features.filter(feature => target.isAncestorOf(feature))
    if (includeSelf) return [target, ...descendants]
    return descendants
  }

  getSiblingsOf(target: OWSResource, include_self = false, withSubtrees = false) {
    const parentFolder = target.getParentFolder()?.replace('/', '\\/') ?? ''
    const regex = withSubtrees ? `^${parentFolder}(\\/\\d+)+$` : `^${parentFolder}(\\/\\d+){1}$`

    return this.features.filter(node => {
      if (!include_self) {
        if (node === target || node.isDescendantOf(target)) return false
      }
      return node.properties.folder && new RegExp(regex).test(node.properties.folder)
    })
  }

  getRightSiblingsOf(target: OWSResource, include_self = false, withSubtrees = false) {
    if (target.properties.folder === undefined) return []
    const targetIndexNumber = target.getFolderIndex()
    const targetNodeIndexPosition = target.properties.folder.split('/').length - 1

    return this.getSiblingsOf(target, include_self, withSubtrees).filter(feature => {
      if (feature.properties.folder === undefined) return false

      const featureFolders = feature.properties.folder.split('/')
      const featureIndexNumber = Number(featureFolders[targetNodeIndexPosition])

      return include_self ?
        featureIndexNumber >= targetIndexNumber :
        featureIndexNumber > targetIndexNumber
    })
  }

  getFirstChildOf(target: OWSResource) {
    return this.getDescandantsOf(target).find((descendant) => descendant.isChildOf(target))
  }

  getFirstChildIndexOf(target: OWSResource) {
    const firstChild = this.getFirstChildOf(target)
    if (firstChild === undefined) return -1
    return this.features.indexOf(firstChild)
  }

  getLastChildOf(target: OWSResource) {
    return this.getDescandantsOf(target).findLast((descendant) => descendant.isChildOf(target))
  }

  getLastChildIndexOf(target: OWSResource) {
    const lastChild = this.getLastChildOf(target)
    if (lastChild === undefined) return -1
    return this.features.indexOf(lastChild)
  }

  getLastChildFoderIndex(target: OWSResource) {
    const lastChild = this.getLastChildOf(target)
    if (lastChild === undefined) return -1
    return getFeatureFolderIndex(lastChild)
  }

  removeFeature(target: OWSResource) {
    const targetSubtree = this.getDescandantsOf(target, true)
    const start = this.features.indexOf(targetSubtree[0])
    const stop = this.features.indexOf(targetSubtree[targetSubtree.length - 1])

    this.features.splice(start, stop - start + 1)

    updateFolders(this.features)

    return this.features
  }

  activateFeature(target: OWSResource, active: boolean = true) {
    target.properties.active = active
    // activate/deactivate all descendants
    this.getDescandantsOf(target, true).forEach(descendant => descendant.properties.active = active)

    // set parent also active if all siblings of target are active
    if (active === true && this.getSiblingsOf(target).every(feature => feature.properties.active === true)) {
      const parent = this.getParentOf(target)
      if (parent !== undefined) {
        parent.properties.active = active
      }
    }
    // deactivate parent to prevent from parend layer using for getmap calls etc.
    else if (active === false) {
      this.getAncestorsOf(target).forEach(ancestor => ancestor.properties.active = active)
    }
    this.calculateCrsIntersection()
    return this.features
  }

  getActiveFeatures() {
    return this.features.filter(feature => feature.properties.active === true)
  }

  async collectWmsCapabilities() {

    type CapabilitityRef = {
      features: OWSResource[]
      href: string
      capabilitites?: Capabilites
    }

    const capabilitityFeatureMap = this.features.map((feature) => {
      const getCapabilitiesOp = feature.getWmsGetCapabilitiesOperation()
      return {
        features: [feature],
        href: getCapabilitiesOp?.href ?? ''
      }
    }).reduce<CapabilitityRef[]>((result, current) => {
      const exists = result.find(feature => feature.href == current.href)
      if (exists === undefined && current.href !== undefined) {
        result.push(current)
      } else if (exists !== undefined && current.href !== undefined) {
        exists.features.push(...current.features)
      }
      return result;
    }, [])

    await Promise.all(capabilitityFeatureMap.map(capRequests => fetch(capRequests.href))).then(
      responses => {
        responses.forEach((response, index) => {
          response.text().then(
            rawCapabilitites => {
              const status = response.status;
              if (status >= 200 && status < 400 && rawCapabilitites !== undefined) {

                capabilitityFeatureMap[index].capabilitites = parseWms(rawCapabilitites);

                this.capabilititesMap[capabilitityFeatureMap[index].href] = {
                  capabilitites: parseWms(rawCapabilitites),
                  features: capabilitityFeatureMap[index].features
                }
              }
            }
          );
        })
      }
    ).catch((error) => {
      console.error('[request failed]', error.message)
    })
  }

  getInheritedCrs(target: OWSResource) {
    const wmsGetMapOp = target.getWmsGetMapOperation()
    const getCapabilitiesOp = target.getWmsGetCapabilitiesOperation()
    const referenceSystems: string[] = []

    if (getCapabilitiesOp !== undefined &&
      getCapabilitiesOp.href in this.capabilititesMap &&
      wmsGetMapOp?.href !== undefined) {

      const getMapUrl = new URL(wmsGetMapOp.href)
      const layers = getMapUrl.searchParams.get('LAYERS') ?? getMapUrl.searchParams.get('layers') ?? ''
      const layerIdentifiers = layers.split(',')

      const capabilitites = this.capabilititesMap[getCapabilitiesOp?.href].capabilitites as WmsCapabilitites
      
      referenceSystems.push(
        ...layerIdentifiers.reduce<string[]>((acc, identifier) => {
          const inheritedProps = collectInheritedLayerProperties(capabilitites.rootLayer, identifier)
          if (inheritedProps !== undefined) {
            acc = [...new Set([...acc, ...inheritedProps.referenceSystems])]
          }
          return acc
        }, [])
      )
    } 

    return referenceSystems
  }

  calculateCrsIntersection() {
    this.crsIntersection = this.getActiveFeatures().reduce<string[]>((acc, feature) => {
      return [...new Set([...acc, ...this.getInheritedCrs(feature)])]
    }, [])
  }
}
