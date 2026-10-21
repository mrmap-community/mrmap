import { normalizeFolderPaths, splitFolderPath } from './folders'
import { OWSContext as IOWSContext, OWSContextProperties, OWSResource as IOWSResource } from './types'

/**
 * Validation and normalization of OWS Context GeoJSON documents following the core requirements class
 * of the OWS Context GeoJSON Encoding Standard (OGC 14-055r2).
 *
 * Both entry points that replace the viewer state - the URL import and the raw JSON editor - run their
 * document through validateOwsContext() first, so a document is judged and normalized by the same rules
 * no matter where it comes from.
 *
 * Severity of an issue:
 * - "error": the document is malformed. It is rejected and the caller keeps the previous context.
 * - "warning": the document is usable but worth reporting. Unsupported offerings and operations, or an
 *   identifier that is not a URI, are unsupported capabilities and not malformed JSON.
 *
 * The grouping of the resources is normalized together with the document: the "folder" member of the
 * standard is optional, its segments may be named and a document does not need to describe the parent
 * groups of a resource, while the layer tree of the viewer works on numbered and complete paths.
 * "normalizeFolderPaths" translates the described grouping onto them and reports every translation it
 * had to do as a warning, so a folderless or named grouping is neither rejected nor lost.
 *
 * Everything that is not part of the core requirements class is an extension and survives the
 * normalization. That explicitly includes the mrmap specific "active" flag on operations, which the
 * layer tree uses to activate GetMap and GetFeatureInfo independently of each other.
 */

/** Specification reference (requirements class) of an OWS Context document. */
export const OWS_CONTEXT_CORE_PROFILE = 'http://www.opengis.net/spec/owc-geojson/1.0/req/core'

/** Offering code of the only offering the viewer is able to render. */
export const WMS_OFFERING_CODE = 'http://www.opengis.net/spec/owc/1.0/req/wms'

/** Operation codes of the WMS offering the viewer makes use of. */
export const SUPPORTED_WMS_OPERATIONS = ['GetCapabilities', 'GetMap', 'GetFeatureInfo']

export type OwsContextIssueSeverity = 'error' | 'warning'

export interface OwsContextIssue {
    severity: OwsContextIssueSeverity
    /** path of the offending member, e.g. "features[3].properties.title" */
    path: string
    message: string
}

export interface OwsContextValidationResult {
    hasErrors: boolean
    issues: OwsContextIssue[]
    /** normalized document, only set when no error was found */
    context?: IOWSContext
}

const SUPPORTED_HTTP_METHODS = ['get', 'post', 'put', 'delete']

const GEOJSON_GEOMETRY_TYPES = [
    'Point', 'MultiPoint', 'LineString', 'MultiLineString', 'Polygon', 'MultiPolygon', 'GeometryCollection'
]

const UUID_IDENTIFIER_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const ABSOLUTE_URI_PATTERN = /^[A-Za-z][A-Za-z0-9+.-]*:/

const RFC_3339_PATTERN = /^\d{4}-\d{2}-\d{2}([Tt ]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})?)?$/

const LANGUAGE_TAG_PATTERN = /^[A-Za-z]{2,3}(-[A-Za-z0-9]{1,8})*$/

const isRecord = (value: unknown): value is Record<string, unknown> =>
    typeof value === 'object' && value !== null && !Array.isArray(value)

const isFilledString = (value: unknown): value is string =>
    typeof value === 'string' && value.trim().length > 0

const isRfc3339 = (value: string) => RFC_3339_PATTERN.test(value) && !Number.isNaN(Date.parse(value))

const isAbsoluteUrl = (value: string) => {
    try {
        new URL(value)
        return true
    } catch {
        return false
    }
}

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T

interface IssueCollector {
    issues: OwsContextIssue[]
    error: (path: string, message: string) => void
    warn: (path: string, message: string) => void
}

const createCollector = (): IssueCollector => {
    const issues: OwsContextIssue[] = []
    return {
        issues: issues,
        error: (path: string, message: string) => issues.push({ severity: 'error', path: path, message: message }),
        warn: (path: string, message: string) => issues.push({ severity: 'warning', path: path, message: message })
    }
}

/**
 * Returns the properties with a "links.profiles" member referencing the core requirements class. The
 * input object is returned as is when it already references it, so callers can detect a change.
 */
export const ensureCoreProfile = (properties: OWSContextProperties): OWSContextProperties => {
    const profiles = Array.isArray(properties.links?.profiles) ? properties.links.profiles : []
    if (profiles.includes(OWS_CONTEXT_CORE_PROFILE)) return properties

    return {
        ...properties,
        links: { ...(properties.links ?? {}), profiles: [...profiles, OWS_CONTEXT_CORE_PROFILE] }
    }
}

/** join issues into a single line, e.g. for the status bar of the viewer */
export const formatOwsContextIssues = (issues: OwsContextIssue[]): string =>
    issues.map(issue => `${issue.path}: ${issue.message}`).join('; ')



const validateDateTime = (collector: IssueCollector, value: unknown, path: string) => {
    if (!isFilledString(value)) {
        collector.error(path, 'is required and must be a RFC 3339 date time string')
        return
    }
    if (!isRfc3339(value)) {
        collector.error(path, `"${value}" is not a RFC 3339 date time string, e.g. "2024-05-03T10:26:38.476Z"`)
    }
}

const validateBBox = (collector: IssueCollector, bbox: unknown, path: string) => {
    if (bbox === undefined) return
    if (!Array.isArray(bbox) || bbox.length < 4 ||
        bbox.some(value => typeof value !== 'number' || !Number.isFinite(value))) {
        collector.error(path, 'must be an array of at least four numbers')
    }
}

const validateGeometry = (collector: IssueCollector, geometry: unknown, path: string) => {
    if (geometry === undefined || geometry === null) return
    if (!isRecord(geometry)) {
        collector.error(path, 'must be a GeoJSON geometry object or null')
        return
    }
    if (typeof geometry.type !== 'string' || !GEOJSON_GEOMETRY_TYPES.includes(geometry.type))
        collector.error(`${path}.type`, 'must be one of the GeoJSON geometry types')
    if (geometry.type === 'GeometryCollection') {
        if (!Array.isArray(geometry.geometries)) collector.error(`${path}.geometries`, 'must be an array of geometries')
        else geometry.geometries.forEach((child, index) => validateGeometry(collector, child, `${path}.geometries[${index}]`))
        return
    }
    if (geometry.coordinates !== undefined && !Array.isArray(geometry.coordinates))
        collector.error(`${path}.coordinates`, 'must be an array')
}

const validateAuthor = (collector: IssueCollector, author: unknown, path: string) => {
    if (!isRecord(author)) {
        collector.error(path, 'must be an object with a "name" member')
        return
    }
    if (!isFilledString(author.name)) collector.error(`${path}.name`, 'is required and must be a non empty string')
}

const validateCategories = (collector: IssueCollector, categories: unknown, path: string) => {
    if (categories === undefined) return
    if (!Array.isArray(categories)) {
        collector.error(path, 'must be an array of categories')
        return
    }
    categories.forEach((category, index) => {
        const categoryPath = `${path}[${index}]`
        if (!isRecord(category)) {
            collector.error(categoryPath, 'must be an object with a "term" member')
            return
        }
        if (!isFilledString(category.term))
            collector.error(`${categoryPath}.term`, 'is required and must be a non empty string')
    })
}

const validateLink = (collector: IssueCollector, link: unknown, path: string) => {
    if (!isRecord(link)) {
        collector.error(path, 'must be an object with a "href" member')
        return
    }
    if (!isFilledString(link.href)) collector.error(`${path}.href`, 'is required and must be a non empty string')
}

/** the standard defines via/alternates/previews as lists and data as a single link, both are accepted */
const validateLinks = (collector: IssueCollector, links: unknown, path: string) => {
    if (links === undefined) return
    if (!isRecord(links)) {
        collector.error(path, 'must be an object')
        return
    }
    ['alternates', 'previews', 'data', 'via'].forEach(member => {
        const value = links[member]
        if (value === undefined) return
        if (Array.isArray(value)) {
            value.forEach((link, index) => validateLink(collector, link, `${path}.${member}[${index}]`))
            return
        }
        validateLink(collector, value, `${path}.${member}`)
    })
}

const validateOperations = (collector: IssueCollector, operations: unknown, path: string, isWmsOffering: boolean) => {
    if (operations === undefined) return
    if (!Array.isArray(operations)) {
        collector.error(path, 'must be an array of operations')
        return
    }
    operations.forEach((operation, index) => {
        const operationPath = `${path}[${index}]`
        if (!isRecord(operation)) {
            collector.error(operationPath, 'must be an object with "code", "method" and "href"')
            return
        }
        if (!isFilledString(operation.code))
            collector.error(`${operationPath}.code`, 'is required and must be a non empty string')
        else if (isWmsOffering && !SUPPORTED_WMS_OPERATIONS.includes(operation.code))
            collector.warn(`${operationPath}.code`, `"${operation.code}" is not supported by the viewer and is kept as an extension`)

        if (!isFilledString(operation.method))
            collector.error(`${operationPath}.method`, 'is required and must be "GET", "POST", "PUT" or "DELETE"')
        else if (!SUPPORTED_HTTP_METHODS.includes(operation.method.toLowerCase()))
            collector.warn(`${operationPath}.method`, `"${operation.method}" is not a supported HTTP method`)

        // the viewer builds its requests with new URL(operation.href), so a relative href is fatal
        if (!isFilledString(operation.href))
            collector.error(`${operationPath}.href`, 'is required and must be a non empty string')
        else if (!isAbsoluteUrl(operation.href))
            collector.error(`${operationPath}.href`, `"${operation.href}" is not an absolute URL`)

        if (operation.type !== undefined && typeof operation.type !== 'string')
            collector.error(`${operationPath}.type`, 'must be a string')
    })
}



const validateOfferings = (collector: IssueCollector, offerings: unknown, path: string) => {
    if (offerings === undefined) return
    if (!Array.isArray(offerings)) {
        collector.error(path, 'must be an array of offerings')
        return
    }
    offerings.forEach((offering, offeringIndex) => {
        const offeringPath = `${path}[${offeringIndex}]`
        if (!isRecord(offering)) {
            collector.error(offeringPath, 'must be an object with a "code" member')
            return
        }
        if (!isFilledString(offering.code)) {
            collector.error(`${offeringPath}.code`, 'is required and must be a non empty string')
            return
        }
        const isWmsOffering = offering.code === WMS_OFFERING_CODE
        if (!isWmsOffering)
            collector.warn(`${offeringPath}.code`, `"${offering.code}" is an offering the viewer cannot render; the resource is kept as an extension`)

        validateOperations(collector, offering.operations, `${offeringPath}.operations`, isWmsOffering)

        if (offering.contents !== undefined) {
            if (!Array.isArray(offering.contents)) collector.error(`${offeringPath}.contents`, 'must be an array of contents')
            else offering.contents.forEach((content, index) => {
                const contentPath = `${offeringPath}.contents[${index}]`
                if (!isRecord(content)) collector.error(contentPath, 'must be an object with a "type" member')
                else if (!isFilledString(content.type)) collector.error(`${contentPath}.type`, 'is required and must be a non empty string')
            })
        }

        if (offering.styles !== undefined) {
            if (!Array.isArray(offering.styles)) collector.error(`${offeringPath}.styles`, 'must be an array of styles')
            else offering.styles.forEach((style, index) => {
                const stylePath = `${offeringPath}.styles[${index}]`
                if (!isRecord(style)) collector.error(stylePath, 'must be an object with a "name" member')
                else if (!isFilledString(style.name)) collector.error(`${stylePath}.name`, 'is required and must be a non empty string')
            })
        }
    })
}

const validateResourceProperties = (
    collector: IssueCollector,
    properties: Record<string, unknown>,
    path: string,
    folderOwners: Map<string, string>,
    ownerPath: string,
) => {
    if (!isFilledString(properties.title))
        collector.error(`${path}.title`, 'is required and must be a non empty string')

    validateDateTime(collector, properties.updated, `${path}.updated`)

    if (properties.active !== undefined && typeof properties.active !== 'boolean')
        collector.error(`${path}.active`, 'must be a boolean')

    if (properties.authors !== undefined) {
        if (!Array.isArray(properties.authors)) collector.error(`${path}.authors`, 'must be an array of authors')
        else properties.authors.forEach((author, index) => validateAuthor(collector, author, `${path}.authors[${index}]`))
    }

    validateCategories(collector, properties.categories, `${path}.categories`)
    validateLinks(collector, properties.links, `${path}.links`)
    validateOfferings(collector, properties.offerings, `${path}.offerings`)

    if (properties.folder === undefined) return

    // a folder may be named and does not need to describe its parent groups, both is normalized onto
    // the numbered paths the layer tree works with, only a folder without any segment is unusable
    if (!isFilledString(properties.folder) || splitFolderPath(properties.folder).length === 0) {
        collector.error(`${path}.folder`, `"${String(properties.folder)}" does not describe a folder, e.g. "/0" or "/root/algal"`)
        return
    }

    const key = splitFolderPath(properties.folder).join('/')
    const duplicate = folderOwners.get(key)
    if (duplicate !== undefined)
        collector.error(`${path}.folder`, `duplicates the folder "${properties.folder}" of ${duplicate}`)
    else folderOwners.set(key, ownerPath)
}

const validateFeatures = (collector: IssueCollector, features: unknown[]) => {
    const folderOwners = new Map<string, string>()

    features.forEach((feature, index) => {
        const path = `features[${index}]`
        if (!isRecord(feature)) {
            collector.error(path, 'must be a GeoJSON Feature object')
            return
        }
        if (feature.type !== 'Feature') collector.error(`${path}.type`, 'must be "Feature"')

        if (feature.id !== undefined && typeof feature.id !== 'string' && typeof feature.id !== 'number')
            collector.error(`${path}.id`, 'must be a string or a number')

        validateBBox(collector, feature.bbox, `${path}.bbox`)
        validateGeometry(collector, feature.geometry, `${path}.geometry`)

        if (!isRecord(feature.properties)) {
            collector.error(`${path}.properties`, 'is required and must be an object')
            return
        }
        validateResourceProperties(collector, feature.properties, `${path}.properties`, folderOwners, path)
    })
}



const validateContextProperties = (collector: IssueCollector, properties: Record<string, unknown>) => {
    const path = 'properties'

    // "lang" is required by the core profile; the mrmap backend has been emitting "language" for it
    if (!isFilledString(properties.lang)) {
        if (isFilledString(properties.language)) {
            properties.lang = properties.language
            collector.warn(`${path}.language`, 'is not an OWS Context member, its value has been mapped to properties.lang')
        } else {
            collector.error(`${path}.lang`, 'is required and must be a RFC-3066 language tag, e.g. "en"')
        }
    } else if (!LANGUAGE_TAG_PATTERN.test(properties.lang)) {
        collector.warn(`${path}.lang`, `"${properties.lang}" does not look like a RFC-3066 language tag`)
    }

    if (!isFilledString(properties.title))
        collector.error(`${path}.title`, 'is required and must be a non empty string')

    validateDateTime(collector, properties.updated, `${path}.updated`)

    if (properties.author !== undefined) validateAuthor(collector, properties.author, `${path}.author`)
    validateCategories(collector, properties.categories, `${path}.categories`)

    const stringMembers = ['publisher', 'rights', 'subtitle']
    stringMembers.forEach(member => {
        if (properties[member] !== undefined && typeof properties[member] !== 'string')
            collector.error(`${path}.${member}`, 'must be a string')
    })

    const generator = properties.generator
    if (generator !== undefined) {
        if (!isRecord(generator)) collector.error(`${path}.generator`, 'must be an object')
        else ['title', 'uri', 'version'].forEach(member => {
            if (generator[member] !== undefined && typeof generator[member] !== 'string')
                collector.error(`${path}.generator.${member}`, 'must be a string')
        })
    }

    const display = properties.display
    if (display !== undefined) {
        if (!isRecord(display)) collector.error(`${path}.display`, 'must be an object')
        else ['pixelWidth', 'pixelHeight', 'mmPerPixel'].forEach(member => {
            const value = display[member]
            if (value !== undefined && (typeof value !== 'number' || !Number.isFinite(value) || value <= 0))
                collector.error(`${path}.display.${member}`, 'must be a positive number')
        })
    }

    const links = properties.links
    if (links !== undefined && !isRecord(links)) {
        collector.error(`${path}.links`, 'must be an object')
        return
    }

    const profiles = links?.profiles
    if (profiles !== undefined &&
        (!Array.isArray(profiles) || profiles.some(profile => !isFilledString(profile))))
        collector.error(`${path}.links.profiles`, 'must be an array of specification references')
}

/**
 * Validates an unknown value, e.g. the parsed response of a context url or the content of the raw JSON
 * editor, against the core requirements class and returns a normalized copy of it. The normalized copy
 * holds the required core metadata (a URI identifier, an RFC-3339 timestamp free of changes and the
 * core profile reference) and the numbered folder structure the layer tree works with, while unknown
 * members are passed through untouched.
 */
export const validateOwsContext = (value: unknown): OwsContextValidationResult => {
    const collector = createCollector()

    if (!isRecord(value)) {
        collector.error('document', 'must be a JSON object holding an OWS Context FeatureCollection')
        return { hasErrors: true, issues: collector.issues }
    }

    const context = clone(value)

    if (context.type !== 'FeatureCollection')
        collector.error('type', `must be "FeatureCollection", found ${JSON.stringify(context.type)}`)

    if (!isFilledString(context.id)) {
        collector.error('id', 'is required and must be a string holding a URI, e.g. "https://..." or "urn:uuid:..."')
    } else if (UUID_IDENTIFIER_PATTERN.test(context.id)) {
        // a bare uuid identifies the document but is not a URI, keep it usable and report the fix
        context.id = `urn:uuid:${context.id}`
        collector.warn('id', `was a bare UUID and has been normalized to "${context.id}"`)
    } else if (!ABSOLUTE_URI_PATTERN.test(context.id) && !context.id.startsWith('/')) {
        collector.warn('id', `"${context.id}" is not a URI, e.g. "https://..." or "urn:uuid:..."`)
    }

    validateBBox(collector, context.bbox, 'bbox')

    if (context.date !== undefined && (!isFilledString(context.date) || !isRfc3339(context.date)))
        collector.error('date', 'must be a RFC 3339 date time string')

    if (isRecord(context.properties)) {
        validateContextProperties(collector, context.properties)

        const properties = ensureCoreProfile(context.properties as OWSContextProperties)
        if (properties !== context.properties) {
            collector.warn('properties.links.profiles', `does not reference the core profile "${OWS_CONTEXT_CORE_PROFILE}", the reference has been added`)
            context.properties = properties
        }
    } else {
        collector.error('properties', 'is required and must be an object')
    }

    if (Array.isArray(context.features)) validateFeatures(collector, context.features)
    else collector.error('features', 'is required and must be an array of OWS Context resources')

    const hasErrors = collector.issues.some(issue => issue.severity === 'error')
    if (hasErrors) return { hasErrors, issues: collector.issues }

    // the grouping is normalized for the document which is handed out, a rejected document is
    // reported as it was given
    if (Array.isArray(context.features)) {
        const grouping = normalizeFolderPaths(context.features as IOWSResource[])
        grouping.issues.forEach(issue => collector.warn(issue.path, issue.message))
        context.features = grouping.features
    }

    return { hasErrors, issues: collector.issues, context: context as unknown as IOWSContext }
}
