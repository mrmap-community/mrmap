import { useEffect, useState } from 'react'

import { type Operation } from 'openapi-client-axios'

import { useHttpClientContext } from '../../context/HttpClientContext'


const useOperation = (operationId: string): Operation | undefined => {
  const { api } = useHttpClientContext()
  const [operation, setOperation] = useState<Operation>()

  useEffect(() => {
    if (operationId !== undefined && operationId !== '' && api !== undefined) {
      const _operation = api.getOperation(operationId)
      if (_operation === undefined) {
        setOperation(undefined)
        return
      }
      setOperation(_operation)
    }
  }, [operationId, api])

  return operation
}

export default useOperation
