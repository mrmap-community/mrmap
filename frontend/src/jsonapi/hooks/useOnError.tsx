import axios from 'axios'
import { useCallback } from "react"
import { useStore } from "react-admin"
import { useSearchParams } from 'react-router-dom'
import { JsonApiDocument, JsonApiErrorObject } from "../types/jsonapi"

const isInvalidSort = (error: JsonApiErrorObject): boolean => {
  if (error.code === 'invalid' && error.detail.includes('sort parameter')) {
    return true
  }
  return false
}

const isInvalidFilter = (error: JsonApiErrorObject): boolean => {
  if (error.code === 'invalid' && error.detail.includes('invalid filter')) {
    return true
  }
  return false
}


const useOnError = (
  preferenceKey: string,
) => {

  const [listParams, setListParams] = useStore(`preferences.${preferenceKey}.listParams`, {})
  const [searchParams, setSearchParams] = useSearchParams()
  
  const onError = useCallback((
    error: Error,
  ): void => {
      /** Custom error handler for jsonApi bad request response
       *
       * possible if:
       *   - attribute is not sortable
       *   - attribute is not filterable
       *   - wrong sparseField
       *   - wrong include option
       *
      */
      if (axios.isAxiosError(error)) {
        if (error?.status === 400) {
          const jsonApiDocument = error.response?.data as JsonApiDocument

          jsonApiDocument?.errors?.forEach((apiError: JsonApiErrorObject) => {
            if (isInvalidSort(apiError)) {
              // remove sort from storage
              setListParams({...listParams, sort: ''})

              // remove sort from current location
              searchParams.delete('sort')
              setSearchParams(searchParams)
            }
            if (isInvalidFilter(apiError)){
              setListParams({...listParams, filter: ''})
              
              searchParams.delete('filter')
              setSearchParams(searchParams)
            }
          })
        } else if (error.status === 401) {
          // TODO
        } else if (error.status === 403) {
          // TODO
        }
      }
  }, [searchParams, listParams, setListParams, setSearchParams])

  return onError

}


export default useOnError