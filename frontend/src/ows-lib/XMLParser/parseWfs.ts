import { WfsCapabilitites, WfsFeatureType, WfsOperation } from './types'
import { getAttribute, getChildren, getDescendantByPath, getDocument, getChild, getText } from './utils'

/**
 * Phase 1 of the WFS viewer epic only parses WFS 2.0.0 capabilities. Older
 * versions advertise different parameter spellings and result paging, so they
 * must be reported as unsupported instead of being parsed as if compatible.
 */
const SUPPORTED_WFS_VERSION = '2.0.0'

const findChildByAttribute = (parent: Element | undefined, localName: string, attribute: string, value: string): Element | undefined => {
  if (!parent) return undefined
  return getChildren(parent, localName).find(element => getAttribute(element, attribute) === value)
}

/**
 * Extracts an answerable value from an ows:Constraint: the DefaultValue when
 * stated, otherwise a single AllowedValues entry. A constraint that answers
 * nothing (e.g. NoValues without a DefaultValue) stays absent; absence must
 * not be read as "unlimited" or "supported" by callers.
 */
const parseConstraint = (constraint: Element): [string, string] | undefined => {
  const name = getAttribute(constraint, 'name')
  if (!name) return undefined
  const defaultValue = getText(constraint, 'DefaultValue')
  if (defaultValue !== undefined) return [name, defaultValue]
  const values = getChildren(getChild(constraint, 'AllowedValues'), 'Value')
    .map(value => value.textContent?.trim())
    .filter((value): value is string => !!value)
  if (values.length === 1) return [name, values[0]]
  return undefined
}

const collectConstraints = (parent: Element | undefined): Record<string, string> => {
  const constraints: Record<string, string> = {}
  if (!parent) return constraints
  for (const constraint of getChildren(parent, 'Constraint')) {
    const entry = parseConstraint(constraint)
    if (entry) {
      constraints[entry[0]] = entry[1]
    }
  }
  return constraints
}

/**
 * WFS services advertise the binding URL either directly on the ows:Get /
 * ows:Post element or on an optional ows:OnlineResource child; an empty href
 * stays empty and is not replaced by the child lookup.
 */
const bindingUrl = (binding: Element | undefined): string | undefined => {
  if (!binding) return undefined
  return getAttribute(binding, 'href', 'xlink:href')
    ?? getAttribute(getChild(binding, 'OnlineResource'), 'href', 'xlink:href')
}

/**
 * One ows:Operation of the OperationsMetadata section. Both bindings and every
 * parameter's AllowedValues are kept with their advertised spellings; the
 * outputFormat AllowedValues double as the operations mimeTypes.
 */
const parseOperation = (operationsMetadata: Element | undefined, name: string): WfsOperation | undefined => {
  const operation = findChildByAttribute(operationsMetadata, 'Operation', 'name', name)
  if (!operation) return undefined

  const http = getDescendantByPath(operation, ['DCP', 'HTTP'])
  const get = bindingUrl(getChild(http, 'Get')) ?? ''
  const post = bindingUrl(getChild(http, 'Post'))

  const parameters: Record<string, string[]> = {}
  for (const parameter of getChildren(operation, 'Parameter')) {
    const parameterName = getAttribute(parameter, 'name')
    if (!parameterName) continue
    parameters[parameterName] = getChildren(getChild(parameter, 'AllowedValues'), 'Value')
      .map(value => value.textContent?.trim())
      .filter((value): value is string => !!value)
  }

  return {
    get,
    post,
    mimeTypes: parameters['outputFormat'] ?? [],
    parameters,
    constraints: collectConstraints(operation)
  }
}

const toBounds = (lower: string | undefined, upper: string | undefined): [number, number, number, number] | undefined => {
  if (!lower || !upper) return undefined
  const [west, south] = lower.trim().split(/\s+/).map(Number)
  const [east, north] = upper.trim().split(/\s+/).map(Number)
  if ([west, south, east, north].some(value => !Number.isFinite(value))) return undefined
  return [west, south, east, north]
}

const parseFeatureType = (featureType: Element): WfsFeatureType => {
  const name = getText(featureType, 'Name')
  if (!name) {
    throw new Error('WFS feature type without a Name cannot be represented')
  }

  const nameElement = getChild(featureType, 'Name')
  const prefix = name.includes(':') ? name.split(':')[0] : undefined
  // resolve the prefix from the namespace declarations in scope of the Name
  const namespaceUri = prefix !== undefined ? nameElement?.lookupNamespaceURI(prefix) ?? undefined : undefined

  const boundingBox = getChild(featureType, 'WGS84BoundingBox')
  const outputFormatsElement = getChild(featureType, 'OutputFormats')

  return {
    metadata: {
      name,
      title: getText(featureType, 'Title') ?? '',
      abstract: getText(featureType, 'Abstract')
    },
    name,
    namespaceUri,
    bounds: toBounds(getText(boundingBox, 'LowerCorner'), getText(boundingBox, 'UpperCorner')),
    defaultCrs: getText(featureType, 'DefaultCRS'),
    otherCrs: getChildren(featureType, 'OtherCRS')
      .map(crs => crs.textContent?.trim())
      .filter((crs): crs is string => !!crs),
    outputFormats: outputFormatsElement
      ? getChildren(outputFormatsElement, 'Format')
        .map(format => format.textContent?.trim())
        .filter((format): format is string => !!format)
      : [],
    metadataUrl: getAttribute(getChild(featureType, 'MetadataURL'), 'href', 'xlink:href')
  }
}

/**
 * Reads an OGC exception answer into the reported code and text, so callers
 * can tell "the service answered" apart from "the answer is not parseable".
 */
const ogcExceptionMessage = (root: Element): string => {
  const exception = getChild(root, 'Exception')
  const code = exception ? getAttribute(exception, 'exceptionCode', 'code') : undefined
  const text = exception
    ? getText(exception, 'exceptionText') ?? getText(exception, 'ExceptionText') ?? exception.textContent?.trim()
    : undefined
  return `OGC exception${code ? ` ${code}` : ''}${text ? `: ${text}` : ''}`
}

const emptyOperation = (): WfsOperation => ({ get: '', post: undefined, mimeTypes: [], parameters: {}, constraints: {} })

export const parseWfs = (xml: string): WfsCapabilitites => {
  const document = getDocument(xml)
  const root = document.documentElement

  if (root.localName === 'ExceptionReport' || root.localName === 'ServiceExceptionReport') {
    throw new Error(ogcExceptionMessage(root))
  }
  if (root.localName !== 'WFS_Capabilities') {
    throw new Error('Not a WFS capabilities document')
  }

  const version = getAttribute(root, 'version') ?? ''
  if (version !== SUPPORTED_WFS_VERSION) {
    throw new Error(`Unsupported WFS version '${version}', only '${SUPPORTED_WFS_VERSION}' is supported`)
  }

  const operationsMetadata = getChild(root, 'OperationsMetadata')
  const getFeature = parseOperation(operationsMetadata, 'GetFeature')
  if (!getFeature) {
    throw new Error('WFS capabilities without a GetFeature operation cannot serve feature layers')
  }

  const identification = getChild(root, 'ServiceIdentification')
  const featureTypesElement = getChild(root, 'FeatureTypeList')

  return {
    version,
    metadata: {
      name: getText(identification, 'Name') ?? '',
      title: getText(identification, 'Title') ?? '',
      abstract: getText(identification, 'Abstract')
    },
    serviceType: getText(identification, 'ServiceType'),
    serviceTypeVersions: getChildren(identification, 'ServiceTypeVersion')
      .map(entry => entry.textContent?.trim())
      .filter((entry): entry is string => !!entry),
    filterConstraints: collectConstraints(getDescendantByPath(root, ['Filter_Capabilities', 'Constraints'])),
    featureTypes: featureTypesElement
      ? getChildren(featureTypesElement, 'FeatureType').map(parseFeatureType)
      : [],
    operationUrls: {
      getCapabilities: parseOperation(operationsMetadata, 'GetCapabilities') ?? emptyOperation(),
      describeFeatureType: parseOperation(operationsMetadata, 'DescribeFeatureType'),
      getFeature
    }
  }
}
