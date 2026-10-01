export type JsonApiMetadata = Record<string, unknown>
export type JsonApiLink = string | { href: string; meta?: JsonApiMetadata }
export type JsonApiLinks = Record<string, JsonApiLink | null>

export const JsonApiMimeType = 'application/vnd.api+json'

/** Non standardized jsonapi pagination info */
export interface JsonApiPaginationInfo {
  page: number
  pages: number
  count: number
}

export interface JsonApiDocument {
  data?: JsonApiPrimaryData[] | JsonApiPrimaryData
  errors?: JsonApiErrorObject[]
  meta?: JsonApiMetadata
  links?: JsonApiLinks
  included?: JsonApiPrimaryData[]
}

export interface JsonApiErrorSource {
  pointer?: string
  parameter?: string
}

export interface JsonApiErrorObject {
  id: string
  links: JsonApiLinks
  status: string
  code: string
  title: string
  detail: string
  source: JsonApiErrorSource
}

export interface ResourceIdentifierObject {
  type: string
  id: string | number
  meta?: JsonApiMetadata
}

export interface ResourceLinkage {
  links?: JsonApiLinks
  data: null | ResourceIdentifierObject | ResourceIdentifierObject[]
  meta?: JsonApiMetadata
}

export interface JsonApiPrimaryData {
  type: string
  id: string | number // TODO: only on patch needed (update)
  links?: JsonApiLinks
  attributes: Record<string, unknown>
  relationships?: Record<string, ResourceLinkage>
}

export interface JsonApiQueryParams {
  [parameter: string]: string | undefined
  include?: string
  fields?: string
}


export interface SparseFieldsets {
  type: string
  fields: string[]
}