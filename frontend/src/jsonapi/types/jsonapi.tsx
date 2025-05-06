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
  meta?: any
  links?: any
  included?: JsonApiPrimaryData[]
}

export interface JsonApiErrorSource {
  pointer?: string
  parameter?: string
}

export interface JsonApiErrorObject {
  id: string
  links: any // TODO: add JsonApiLinkObject
  status: string
  code: string
  title: string
  detail: string
  source: JsonApiErrorSource
}

export interface ResourceIdentifierObject {
  type: string
  id: string | number
  meta?: any
}

export interface ResourceLinkage {
  links?: any
  data: null | ResourceIdentifierObject | ResourceIdentifierObject[]
  meta?: any
}

export interface JsonApiPrimaryData {
  type: string
  id: string | number // TODO: only on patch needed (update)
  links?: any // TODO: add JsonApiLinkObject
  attributes: any
  relationships?: Record<string, ResourceLinkage>
}

export interface JsonApiQueryParams {
  include?: string
  fields?: string
}


export interface SparseFieldsets {
  type: string
  fields: string[]
}