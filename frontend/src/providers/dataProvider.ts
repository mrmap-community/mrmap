import { CreateResult, GetListResult, GetOneResult, HttpError, type CreateParams, type DataProvider, type DeleteManyParams, type DeleteParams, type DeleteResult, type GetListParams, type GetManyParams, type GetManyReferenceParams, type GetOneParams, type Identifier, type Options, type RaRecord, type UpdateManyParams, type UpdateParams, type UpdateResult } from 'react-admin'

import jsonpointer from 'jsonpointer'
import OpenAPIClientAxios, { AxiosInstance, AxiosRequestConfig, AxiosResponse, Operation, type ParamsArray } from 'openapi-client-axios'
import { WebSocketLike } from 'react-use-websocket/dist/lib/types'

import axios, { AxiosError } from 'axios'
import { isEqual } from 'lodash'
import { type JsonApiDocument, type JsonApiPrimaryData } from '../jsonapi/types/jsonapi'
import { capsulateJsonApiPrimaryData, encapsulateJsonApiPrimaryData } from '../jsonapi/utils'
import { getAuthToken } from './authProvider'
import i18nProvider from './i18nProvider'
import { updateSystemTime } from './systemTimeProvider'


type search = (
  query: string,
  options?: SearchOptions
) => Promise<{ data: SearchResult[]; total: number }>;

export interface SearchOptions {
  targets?: string[];
  [key: string]: any;
}

export interface SearchResult {
  id: Identifier;
  type: string;
  url: string;
  content: any;
  matches?: any;
}

export interface SearchResults { 
  data: SearchResult[]; 
  total: number;
}


export interface RelatedResource {
  resource: string
  id: Identifier
}

export interface GetListJsonApiParams extends GetListParams {
  meta?: {
    relatedResource?: RelatedResource
    jsonApiParams?: any
  }
}

export interface JsonApiDataProviderOptions extends Options {
  httpClient: OpenAPIClientAxios
  total?: string
  systemTime?: string
  realtimeBus?: WebSocketLike
}

type EventTypes = 'created' | 'updated' | 'deleted'

export interface MrMapMessage {
  topic: string
  event: {
    type: EventTypes
    payload: {
      ids: Identifier[]
      records?: JsonApiPrimaryData[]
    }
  }
}

export interface CrudEvent {
  type: EventTypes
  payload: {
    ids: Identifier[] // basic event type https://marmelab.com/react-admin/RealtimeDataProvider.html#crud-events
    records?: RaRecord[] // custom extension to provide the records which are passed by the real time bus
  }
}

export interface CrudMessage {
  topic: string
  event: CrudEvent
}

export interface Subscription {
  topic: string
  callback: (event: CrudEvent) => void
}

class OperationNotFoundError extends Error {
  constructor(operationId: string) {
    super(`Operation '${operationId}' not found.`);
    this.name = "OperationNotFoundError";
  }
}

let subscriptions: Subscription[] = []


const handleOperationNotFoundError = (): void => {

}

const buildQueryParams = (params: GetListParams | GetManyParams | GetManyReferenceParams) => {
  const parameters: ParamsArray = []

  const relatedResource = params.meta?.relatedResource
  relatedResource && parameters.push({ name: `${relatedResource.resource}Id`, value: relatedResource.id, in: 'path' })

  const hasPagination = "pagination" in params
  const hasSort = "sort" in params && params.sort?.field && params.sort?.field !== ''

  const hasFilter = "filter" in params // GetListParams && GetManyReferenceParams specific
  const hasIds = "ids" in params // GetManyParams specific
  const hasId = "id" in params  // GetManyReferenceParams specific

  hasPagination && params.pagination !== undefined && parameters.push({ name: 'page[number]', value: params.pagination.page })
  hasPagination && params.pagination !== undefined && parameters.push({ name: 'page[size]', value: params.pagination.perPage })
  hasSort && params.sort !== undefined && parameters.push(   { name: 'sort', value: `${params.sort.order === 'ASC' ? '' : '-'}${params.sort.field}` })

  hasFilter && params.filter !== undefined && Object.entries(params.filter ?? {}).forEach(([filterName, filterValue]) => {
    const _filterName = filterName.includes('_filter_lookup_') ? filterName.replace('_filter_lookup_', '.') : filterName
    if (Array.isArray(filterValue)){
      parameters.push({ name: `filter[${_filterName}.in]`, value: filterValue.map((f: RaRecord) => f.id).join(',') })
    } else if (typeof filterValue === 'object'){
      // in case of geojson filter possible...
      parameters.push({ name: `filter[${_filterName}]`, value: JSON.stringify(filterValue) })
    } else {
      parameters.push({ name: `filter[${_filterName}]`, value: filterValue as string})
    }
  })

  // json:api specific stuff like 'include' or 'fields[Resource]'
  Object.entries(params.meta?.jsonApiParams ?? {}).forEach(([key, value]) => { 
    parameters.push({ name: key, value: typeof value === 'string' ? value : '' }) 
  })

  // GetMany request with list of ids as a filter
  if (hasIds) {
    const ids = params.ids.map(value => typeof value === 'object' ? value.id : value)
    parameters.push({ name: 'filter[id.in]', value: ids.join(',') })
  } 

  if (hasId) { 
    typeof params.id === 'object' ? parameters.push({name: 'filter[id.in]', value: params.id.id}): parameters.push({name: 'filter[id.in]', value: params.id})
  }

  return parameters
}

const  handleListRequest = async (client: AxiosInstance, conf: AxiosRequestConfig, totalPath: string, systemTimePath: string): Promise<GetListResult> => {
  return await client
  .request(conf)
  .then((response: AxiosResponse) => {
    const jsonApiDocument = response.data as JsonApiDocument
    const resources = jsonApiDocument.data as JsonApiPrimaryData[]
    return {
      data: resources.map((data: JsonApiPrimaryData) => Object.assign(
        encapsulateJsonApiPrimaryData(jsonApiDocument, data)
      )),
      total: getTotal(jsonApiDocument, totalPath),
      pageInfo: {
        hasNextPage: jsonApiDocument.links && jsonApiDocument.links.next !== null,
        hasPreviousPage: jsonApiDocument.links && jsonApiDocument.links.prev !== null
      },
      meta: {
        systemTime: getSystemTime(jsonApiDocument, systemTimePath)
      }
    }
  })
}

const getTotal = (response: JsonApiDocument, total: string): number => {
  const _total = jsonpointer.get(response, total)
  if (typeof _total === 'string') {
    return parseInt(_total, 10)
  }
  return _total
}


const getSystemTime = (response: JsonApiDocument, systemTime: string): string | undefined => {
  const _systemTime = jsonpointer.get(response, systemTime)
  const fixed = _systemTime?.replace(/(\.\d{3})\d*/, '$1');
  if (fixed === undefined){
    return
  } 
  updateSystemTime(fixed)
  return fixed;
}


const realtimeOnMessage = (event: MessageEvent): void => {
  const data = JSON.parse(event?.data) as MrMapMessage

  const raEvent = { ...data.event }
  raEvent.payload.records = data.event.payload.records?.map(jsonApiPrimaryData => encapsulateJsonApiPrimaryData(undefined, jsonApiPrimaryData))

  // fire callback functions
  subscriptions.filter(
    subscription =>
      subscription.topic === data.topic)
    .forEach(
      observer => { observer.callback(raEvent) })
}

const checkOperationExists = (api: OpenAPIClientAxios, operationId: string): Operation => {
  const operation = api.getOperation(operationId)
  if (operation === undefined) {
    throw new OperationNotFoundError(operationId)
  }
  return operation
}

const handleBadRequest = (error: AxiosError) => {
  if (error.response?.data?.hasOwnProperty("errors")){

    const jsonApiResponse = error.response.data as JsonApiDocument
    const jsonApiErrors = jsonApiResponse.errors
    
    const raErrorPayload: any = {
        errors: {
        }
    }

    jsonApiErrors?.forEach(jsonApiError => {
      if (jsonApiError.source.pointer !== undefined) {
        // https://jsonapi.org/format/#error-objects
        const fieldName = jsonApiError.source.pointer?.replace('/data/attributes/', '').replace('/data/relationships/', '')

        if (jsonApiError.source.pointer.includes("/data/id")){
          raErrorPayload.errors["id"] = jsonApiError.detail
        } else if (fieldName === undefined) {
          raErrorPayload.errors["root"] = jsonApiError.detail
        } else {
          raErrorPayload.errors[fieldName] = jsonApiError.detail
        }
      } 
    })
    throw new HttpError(error.message, 400, raErrorPayload)
  } else {
    throw new HttpError(error.message, 400)
  }
}


const attachAuthenticationIfExists = (config: AxiosRequestConfig): AxiosRequestConfig => {
  const storedAuthToken = getAuthToken();
  if (storedAuthToken?.token && config.headers){
    config.headers.setAuthorization(`Token ${storedAuthToken?.token}`)
  }
  return config
}

const attachLocalHeader = (config: AxiosRequestConfig): AxiosRequestConfig => {
  if (config.headers){
    config.headers.set("Accept-Language", i18nProvider.getLocale())
  }
  return config
}

const attachHeaders = (config: AxiosRequestConfig): AxiosRequestConfig => {
  const cfg = attachAuthenticationIfExists(config)
  return attachLocalHeader(cfg)
}

const dataProvider = ({
  total = '/meta/pagination/count',
  systemTime = '/meta/systemTime',
  httpClient,
}: JsonApiDataProviderOptions): DataProvider => {  

  
  const updateResource = async (resource: string, params: UpdateParams, systemTimePath: string): Promise<UpdateResult<any>> => {
    const operationId = `partial_update_${resource}`
    const operation = checkOperationExists(httpClient, operationId)
    const partialData: Partial<RaRecord> = {id: params.id}
    Object.keys(params.data).forEach((key) => {
      if (!params.data.hasOwnProperty(key) && params.previousData.hasOwnProperty(key)) return
      
      if ( !isEqual(params.data[key], params.previousData[key]) ) {
        partialData[key] = params.data[key]
      }
    })

    const conf = httpClient.client.api.getAxiosConfigForOperation(operationId, [{ id: params.id }, { data: capsulateJsonApiPrimaryData(partialData, resource, operation) }, attachHeaders(httpClient.axiosConfigDefaults)])
    return await httpClient.client
      .request(conf)
      .then((response: AxiosResponse) => {
        const jsonApiDocument = response.data as JsonApiDocument
        const jsonApiResource = jsonApiDocument.data as JsonApiPrimaryData
        

        return { 
          data: encapsulateJsonApiPrimaryData(jsonApiDocument, jsonApiResource),
          meta: {
            systemTime: getSystemTime(jsonApiDocument, systemTimePath)
          }
        }
      }).catch((error) => {
        if (axios.isAxiosError(error) && error.status === 400) {
          handleBadRequest(error)
        }
        throw error
      }) 
  }

  const deleteResource = async (resource: string, params: DeleteParams): Promise<DeleteResult<any>> => {
    const operationId = `destroy_${resource}`
    checkOperationExists(httpClient, operationId)
    
    const conf = httpClient.client.api.getAxiosConfigForOperation(operationId, [{ id: params.id }, undefined, attachHeaders(httpClient.axiosConfigDefaults)])
      return await httpClient.client.request(conf).then((response: AxiosResponse) => {
      return { data: { id: params.id } }
    })
  }
  return {
    getList: async (resource: string, params: GetListJsonApiParams) => {
      const relatedResource = params.meta?.relatedResource
      if (relatedResource !== undefined && relatedResource.id === undefined){
        // possible if the getList is called inside a CreateGuesser with a ReferenceManyInput as child component. 
        // Therewhile the parent object isnt created and the getList is called with an undefined id. This results in 404 requests.
        return 
      }
      const operationId = relatedResource === undefined ? `list_${resource}` : `list_related_${resource}_of_${relatedResource.resource}`

      checkOperationExists(httpClient, operationId)
      
      const parameters = buildQueryParams(params)
      const conf = httpClient.getAxiosConfigForOperation(operationId, [parameters, undefined, attachHeaders(httpClient.axiosConfigDefaults)])
      
      return await handleListRequest(httpClient.client, conf, total, systemTime)
    },

    getOne: async (resource: string, params: GetOneParams): Promise<GetOneResult> => {
      if (params.id === undefined) {
        return { data: { id: '' } }
      }
      
      const parameters: ParamsArray = [{
        name: 'id',
        value: params.id,
        in: 'path'
      }]
      // json:api specific stuff like 'include' or 'fields[Resource]'
      Object.entries(params.meta?.jsonApiParams ?? {}).forEach(([key, value]) => { parameters.push({ name: key, value: typeof value === 'string' ? value : '' }) })

      let conf = undefined;
      try {
        conf = httpClient.getAxiosConfigForOperation(`retrieve_${resource}`, [parameters, undefined, attachHeaders(httpClient.axiosConfigDefaults)])
      } catch (error) {
        handleOperationNotFoundError();
        return  { data: [], }
      }

      return await httpClient.client.request(conf).then((response: AxiosResponse) => {
        const jsonApiDocument = response.data as JsonApiDocument
        const jsonApiResource = jsonApiDocument.data as JsonApiPrimaryData
        return { 
          data: encapsulateJsonApiPrimaryData(jsonApiDocument, jsonApiResource),
          meta: {
            systemTime: getSystemTime(jsonApiDocument, systemTime)
          }
        }
      })
    },

    getMany: async (resource: string, params: GetManyParams) => {
      const operationId = `list_${resource}`
      checkOperationExists(httpClient, operationId)

      const parameters = buildQueryParams(params)
      const conf = httpClient.getAxiosConfigForOperation(operationId, [parameters, undefined, attachHeaders(httpClient.axiosConfigDefaults)])
      
      return await handleListRequest(httpClient.client, conf, total, systemTime)
    },

    getManyReference: async (resource: string, params: GetManyReferenceParams) => {
      const operationId = `list_${resource}`
      checkOperationExists(httpClient, operationId)

      const parameters = buildQueryParams(params)
      const conf = httpClient.getAxiosConfigForOperation(`list_${resource}`, [parameters, undefined, attachHeaders(httpClient.axiosConfigDefaults)])

      return await handleListRequest(httpClient.client, conf, total, systemTime)
    },

    create: async (resource: string, params: CreateParams): Promise<CreateResult> => {
      const operationId = `create_${resource}`
      const operation = checkOperationExists(httpClient, operationId)

      const conf = httpClient.getAxiosConfigForOperation(operationId, [undefined, { data: capsulateJsonApiPrimaryData(params.data, resource, operation) }, attachHeaders(httpClient.axiosConfigDefaults)])

      return await httpClient.client.request(conf).then((response) => {
        const jsonApiDocument = response.data as JsonApiDocument
        const jsonApiResource = jsonApiDocument.data as JsonApiPrimaryData
        return { data: encapsulateJsonApiPrimaryData(jsonApiDocument, jsonApiResource) }
      }).catch(async error => {
        if (error.response.status === 400) {
          handleBadRequest(error)
        }
        throw error
      })
    },
    update: async (resource: string, params: UpdateParams) =>
      await updateResource(resource, params, systemTime),

    updateMany: async (resource: string, params: UpdateManyParams) => {
      // Hacky many update via for loop. JSON:API does not support many update in a single transaction.
      const results: Identifier[] = []

      for (const id of params.ids) {
        await updateResource(
          resource,
          {
            id,
            data: params.data,
            previousData: {}
          },
          systemTime
        ).then((data) => {
          results.push(data.data.id)
        })
      }

      return await Promise.resolve({ data: results })
    },

    delete: async (resource: string, params: DeleteParams) =>
      await deleteResource(resource, params),
    deleteMany: async (resource: string, params: DeleteManyParams) => {
      const results: Identifier[] = []
      for (const id of params.ids) {
        await deleteResource(
          resource, { id }
        ).then((data) => {
          results.push(data.data.id)
        })
      }
      return await Promise.resolve({ data: results })
    },

    // async realtime features
    subscribe: async (topic: string, callback: (event: CrudEvent) => void) => {
      //createRealtimeSocket(realtimeBus)
      subscriptions.push({ topic, callback })
      return await Promise.resolve({ data: null })
    },
    unsubscribe: async (topic: string, callback: (event: CrudEvent) => void) => {
      subscriptions = subscriptions.filter(
        subscription =>
          subscription.topic !== topic ||
          subscription.callback !== callback
      )
      return await Promise.resolve({ data: null })
    },
    publish: async (topic: string, event: CrudEvent) => {
      if (topic === undefined || topic === '') {
        return await Promise.reject(new Error('missing topic'))
      }
      if (event.type === undefined) {
        return await Promise.reject(new Error('missing event type'))
      }
      subscriptions.forEach(
        subscription => {
          topic === subscription.topic &&
            subscription.callback(event)
        }
      )
      return await Promise.resolve({ data: null })
    },
    attachRealtimeOnMessage: async (realtimeBus: WebSocket | undefined) => {
      realtimeBus && (realtimeBus.onmessage = realtimeOnMessage)
    },
    search: async (query: string, options?: SearchOptions): Promise<SearchResults>=> {
      const targets = options?.targets || []
      const searchResults: SearchResults = {
        data: [],
        total: 0
      }
      
      for (const target of targets) {
        const operationId = `list_${target}` 

        checkOperationExists(httpClient, operationId)
        
        const parameters = buildQueryParams({filter: {search: query}})
        const conf = httpClient.getAxiosConfigForOperation(operationId, [parameters, undefined, attachHeaders(httpClient.axiosConfigDefaults)])
        
        await handleListRequest(httpClient.client, conf, total).then((data) => {
          searchResults.data.push(...data.data.map(record => ({
            id: `${target}-${record.id}`,
            type: target,
            url: `/${target}/${record.id}`,
            content: {
              id: record.id,
              label: record.stringRepresentation,
              description: ''
            }
          }
          )))
        })
      }

      searchResults.total = searchResults.data.length

      return await Promise.resolve(searchResults)
    }
  }
}

export default dataProvider
