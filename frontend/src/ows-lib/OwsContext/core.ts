import { BBox, Geometry } from 'geojson';
import { v4 as uuidv4 } from 'uuid';

import { parseWms } from '../XMLParser/parseCapabilities';
import { parseWfs } from '../XMLParser/parseWfs';
import { migrateLegacyAuthentications } from './authentication';
import { Position } from './enums';
import { compareFolderPaths, normalizeFolderPaths } from './folders';
import { OWSContext as IOWSContext, OWSResource as IOWSResource, Operation, OWSContextProperties, OWSResourceProperties, Authentication } from './types';
import { appendWmsOperationParameters, areWmsOperationsCompatible, getFeatureFolderIndex, getParentFolder, isDescendant, prepareGetCapabilititesUrl, treeToList, updateFolders, wfsToOWSResources, wmsToOWSResources } from './utils';
import { ensureCoreProfile, isWmsOfferingCode, isWfsOfferingCode, normalizeResourceProperties } from './validation';

const VALID_PATH = /(\/\d*)+/


export interface OptimizedUrlsMap {
  features: OWSResource[]
  url: URL, 
  operations: Operation[]
}

export class OWSResource implements IOWSResource {
  properties: OWSResourceProperties;
  geometry?: Geometry;
  type: 'Feature';
  id?: string | number;
  bbox?: BBox;
  children: OWSResource[];

  constructor(
    properties: OWSResourceProperties,
    id: string | number = uuidv4(),
    bbox: BBox | undefined = undefined,
    geometry: Geometry | undefined = undefined,
    children: OWSResource[] | undefined = []
  ) {
    this.properties = normalizeResourceProperties(properties)
    this.id = id
    this.bbox = bbox ? JSON.parse(JSON.stringify(bbox)) : undefined
    this.type = 'Feature'
    this.geometry = geometry ? JSON.parse(JSON.stringify(geometry)) : undefined
    this.children = children ?? []
  }

  static fromPlainObject(resource: IOWSResource): OWSResource {
    const children = resource.children?.map(child => OWSResource.fromPlainObject(child))
    return new OWSResource(resource.properties, resource.id, resource.bbox, resource.geometry, children)
  }

  getWmsOffering() {
    return this.properties.offerings?.find(offering => isWmsOfferingCode(offering.code))
  }

  getWmsOperationByCode(code: string) {
    const wmsOffering = this.getWmsOffering()
    if (wmsOffering !== undefined) {
      return wmsOffering.operations?.find(operation => operation.code === code)
    }
  }

  getWfsOffering() {
    return this.properties.offerings?.find(offering => isWfsOfferingCode(offering.code))
  }

  getWfsOperationByCode(code: string, method: string = 'GET') {
    const wfsOffering = this.getWfsOffering()
    if (wfsOffering !== undefined) {
      return wfsOffering.operations?.find(operation =>
        operation.code === code && operation.method.toLowerCase() === method.toLowerCase())
    }
  }

  getFolderIndex() {
    return getFeatureFolderIndex(this)
  }

  getParentFolder = () => {
    if (this.properties.folder?.split('/').length === 2) return // root node
    return this.properties.folder?.split('/').slice(0, -1).join('/')
  }

  isRootNode = () => {
    return this.properties.folder?.split('/').length === 2
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
  folderToResource: Map<string, OWSResource>;
  authentications?: Authentication[];
  authenticationHeaders?: import('./contrib').HeaderAuthentication[];

  constructor(
    id: string = `urn:uuid:${uuidv4()}`,
    features: (OWSResource | IOWSResource)[] = [],
    bbox: BBox = [-180, -90, 180, 90],
    properties: OWSContextProperties = {
      lang: 'en',
      title: 'mrmap ows context',
      updated: new Date().toISOString()
    },
  ) {
    this.folderToResource = new Map<string, OWSResource>();
    this.id = id;
    this.type = "FeatureCollection";
    // whatever grouping the given resources describe, the viewer works on numbered and complete
    // folder paths, so they are normalized onto them before they become the state of the viewer
    this.features = normalizeFolderPaths(features).features.map(OWSResource.fromPlainObject);
    this.rebuildFolderLookup()
    this.bbox = bbox;
    // every document the viewer creates references the core requirements class of the standard
    this.properties = ensureCoreProfile(JSON.parse(JSON.stringify(properties)));
  }
  [name: string]: unknown;

  static fromPlainObject(ctx: IOWSContext) {
    const context = new OWSContext(
        ctx.id,
        ctx.features.map(OWSResource.fromPlainObject),
        ctx.bbox,
        ctx.properties,
    );

    // Preserve any additional properties from the input object
    if (ctx.date) {
      context.date = ctx.date;
    }

    // Copy any other custom properties that aren't part of the standard interface
    for (const [key, value] of Object.entries(ctx)) {
      if (!['id', 'features', 'bbox', 'properties', 'date', 'type', 'folderToResource'].includes(key)) {
        (context as Record<string, unknown>)[key] = value;
      }
    }

    migrateLegacyAuthentications(context);
    return context;
  }

  private rebuildFolderLookup() {
    this.folderToResource.clear();

    for (const feature of this.features) {
      const folder = feature.properties.folder;
      if (folder) {
        this.folderToResource.set(folder, feature);
      }
    }
  }

  appendWms(href: string, capabilitites: string): number {

    const parsedWms = parseWms(capabilitites)

    const url = prepareGetCapabilititesUrl(href, 'WMS')

    const treeId = this.getNextRootId()

    const additionalFeatures = wmsToOWSResources(url.href, parsedWms, treeId).map(
      resource => new OWSResource(resource.properties, resource.id, resource.bbox, resource.geometry, resource.children)
    )

    this.features.push(...additionalFeatures)

    this.rebuildFolderLookup()

    return treeId
  }

  /**
   * Appends parsed WFS capabilities as a new tree of resources: a root node for the service and one
   * leaf per feature type. The existing trees and the area of interest of the document stay
   * untouched, so importing a WFS never disturbs the WMS selections of a mixed map. Returns the id
   * of the new tree, as appendWms does.
   */
  appendWfs(href: string, capabilities: string): number {

    const parsedWfs = parseWfs(capabilities)

    const url = prepareGetCapabilititesUrl(href, 'WFS', parsedWfs.version)

    const treeId = this.getNextRootId()

    const additionalFeatures = wfsToOWSResources(url.href, parsedWfs, treeId).map(
      resource => new OWSResource(resource.properties, resource.id, resource.bbox, resource.geometry, resource.children)
    )

    this.features.push(...additionalFeatures)

    this.rebuildFolderLookup()

    return treeId
  }

  findResourceByFolder(folder?: string) {
    return folder
        ? this.folderToResource.get(folder)
        : undefined;
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

  isMoveNeeded(source: OWSResource, target: OWSResource, position: Position) {
    if (target.properties.folder === undefined ||
      source.properties.folder === undefined ||
      source === target
    ) return false

    if (source.isSiblingOf(target)){
      if (position === Position.left && source.getFolderIndex() === target.getFolderIndex() -1){
        //console.log('no move needed. source is left sibling of target')
        return false
      }
      if (position === Position.right && source.getFolderIndex() - 1 === target.getFolderIndex()){
        //console.log('no move needed. source is right sibling of target.')
        return false
      }
    }

    if (position === Position.firstChild && source.isChildOf(target)) {
      if (source.getFolderIndex() === 0){
        //console.log('no move needed. source is the first child of target')
        return false
      } 
    }

    if (position === Position.lastChild && source.isChildOf(target)) {
      if (source.getFolderIndex() === this.getLastChildFoderIndex(target)){
        //console.log('no move needed. source is the last child of target')
        return false
      } 
    }

    return true
  }

  moveFeature(source: OWSResource, target: OWSResource, position: Position = Position.lastChild): OWSResource[] {
    if (!this.isMoveNeeded(source, target, position)) return this.features

    this.validateFolderStructure()

    
    // first of all, get the objects before manipulating data. 
    // All filter functions will retun subsets with shallow copys
    const currentSourceSubtree = this.getDescandantsOf(source, true)
    const currentSourceSiblings = this.getSiblingsOf(source, false, false)
    const currentSourceSiblingtrees = this.getSiblingsOf(source, false, true)

    const currentSourceParentFolder = source.getParentFolder() ?? '/'
    const currentSourceFolders = currentSourceSubtree.map(node => node.properties.folder).filter(folder => folder !== undefined)

    const futureSiblings = this.getDescandantsOf(target, false).filter(descendant => descendant.properties.folder && !currentSourceFolders.includes(descendant.properties.folder))

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
    this.rebuildFolderLookup()
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
    this.rebuildFolderLookup()
  }

  sortFeaturesByFolder() {
    this.features.sort((a, b) => compareFolderPaths(a.properties.folder, b.properties.folder));
    this.rebuildFolderLookup()
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
      const parentFolder = target.getParentFolder();

      if (!parentFolder || parentFolder === '/') {
          return;
      }

      return this.folderToResource.get(parentFolder);
  }

  getAncestorsOf(target: OWSResource, include_self: boolean = false) {
    const ancestors = this.features.filter(feature => target.isDescendantOf(feature))
    if (include_self) return [...ancestors, target]
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
    this.rebuildFolderLookup()
    return this.features
  }

  activateFeature(folder?: string, active: boolean = true) {
    const target = this.findResourceByFolder(folder)
    if (target === undefined) return []
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
    return this.features
  }

  getActiveFeatures() {
    return this.features.filter(feature => feature.properties.active === true)
  }

  /**
   * Build optimized GetMap or GetFeatureInfo URLs for WMS features.
   * @param featureFilter Optional predicate to select features. If omitted,
   * the default behavior is to include features that have a WMS offering and
   * are marked active (`feature.properties.active === true`).
   * The optional operation comparator can restrict the shared compatibility rules further.
   */
  getOptimizedUrlsByCode(
    code: string, 
    featureFilter?: (feature: OWSResource) => boolean,
    operationCompareFn?: (index: number, offeringA: Operation, offeringB: Operation) => boolean,
  ): OptimizedUrlsMap[] {
    const trees = this.treeify()
    const urls: OptimizedUrlsMap[] = []
    
    /** 
     * every tree is 1..* atomic wms
     */
    trees.forEach((tree) => {
      const activeWmsFeatures = treeToList(tree).filter(feature => {
        if (typeof featureFilter === 'function') return featureFilter(feature)
        return feature.properties.offerings?.find(offering => isWmsOfferingCode(offering?.code)) && feature.properties.active
      })
      activeWmsFeatures.forEach((feature, index) => {
        const operation = feature.properties.offerings?.find(offering =>
          isWmsOfferingCode(offering.code))?.operations?.find(operation =>
            operation.code === code && operation.method.toLowerCase() === 'get')

        if (operation?.href === undefined) return

        const operationUrl = new URL(operation.href)
        const lastUrl = urls.slice(-1)?.[0]
        const lastOperation = lastUrl?.operations.slice(-1)?.[0]
        
        // A caller may restrict batching further, but cannot override request compatibility.
        const areOfferingsMergeable = lastOperation !== undefined &&
          areWmsOperationsCompatible(lastOperation, operation) &&
          (operationCompareFn === undefined || operationCompareFn(index, lastOperation, operation))

        if (index === 0 || !areOfferingsMergeable) {
          // index 0 signals always a root node ==> just push it; nothing else to do here
          // index > 0 and offerings are not mergeable => define new atomic wms; not mergeable resources
          urls.push({features: [feature], url: operationUrl, operations: [operation]})
          
        }
        else if (areOfferingsMergeable) {
          lastUrl.operations.push(operation)
          lastUrl.features.push(feature)
          appendWmsOperationParameters(lastUrl.url, operationUrl, code)
        }
      })
    })
    return urls
  }

  /**
   * The GetFeatureInfo requests of the filtered features, one per queried layer. WMS counts
   * FEATURE_COUNT per layer, but servers spend it on the whole answer, so a query of several layers
   * reports only as many features as fit in total and leaves the later layers empty without an
   * error. Every queried layer needs its own request to get its own features, the way the WFS
   * feature types already keep their requests apart. The descriptor of a layer stays as it is: only
   * a query subset which names several layers at once is narrowed down to one of them, so its map
   * layers and positional styles remain intact. GetMap batching is deliberately untouched - all
   * layers of one service still share one map request.
   */
  getFeatureInfoRequestsPerLayer(
    featureFilter?: (feature: OWSResource) => boolean
  ): OptimizedUrlsMap[] {
    return this.getOptimizedUrlsByCode(
      'GetFeatureInfo',
      featureFilter,
      // never combine the offerings of two layers into one query
      () => false
    ).flatMap(request => {
      const key = [...request.url.searchParams.keys()]
        .find(name => name.toUpperCase() === 'QUERY_LAYERS')
      const layers = key === undefined
        ? []
        : request.url.searchParams.get(key)!.split(',').filter(layer => layer !== '')
      if (layers.length <= 1) return [request]
      return layers.map(layer => {
        const url = new URL(request.url.href)
        url.searchParams.set(key!, layer)
        return { features: request.features, operations: request.operations, url }
      })
    })
  }

  /**
   * Build the GetFeature request descriptors of the active WFS features. Every feature type keeps
   * its own descriptor: unrelated types and endpoints are never combined into one shared request,
   * so the WMS batching of getOptimizedUrlsByCode does not apply here. A POST binding stays an
   * advertised alternative without a descriptor in phase 1 and WMS features never appear.
   */
  getWfsFeatureRequests(
    featureFilter?: (feature: OWSResource) => boolean
  ): { feature: OWSResource, operation: Operation }[] {
    return this.features
      .filter(feature => {
        if (typeof featureFilter === 'function') return featureFilter(feature)
        return feature.properties.active === true && feature.getWfsOffering() !== undefined
      })
      .map(feature => ({ feature, operation: feature.getWfsOperationByCode('GetFeature', 'GET') }))
      .filter((descriptor): descriptor is { feature: OWSResource, operation: Operation } =>
        descriptor.operation !== undefined && descriptor.operation.href.length > 0)
  }

  /**
   * Build the trees the layer tree and the request building work on. The grouping of the features is
   * normalized first, so resources without a folder, documents which name their groups and documents
   * which do not describe their parent groups stay usable. Every tree holds the resources of one root
   * folder and keeps the id of the resource it was created from.
   */
  treeify(): OWSResource[] {
    const trees: OWSResource[] = []
    const nodes = new Map<string, OWSResource>()

    normalizeFolderPaths(this.features).features.forEach((feature: IOWSResource) => {
      const node = OWSResource.fromPlainObject({ ...feature, children: [] })
      const parentFolder = feature.properties.folder === undefined
        ? undefined
        : getParentFolder(feature.properties.folder)
      const parent = parentFolder === undefined ? undefined : nodes.get(parentFolder)

      nodes.set(node.properties.folder ?? '', node)

      if (parent === undefined) trees.push(node)
      else parent.children.push(node)
    })

    return trees
  }
}
