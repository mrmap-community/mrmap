import { RaRecord, useRecordContext, useResourceContext } from 'react-admin';
import { FieldDefinition } from '../utils';
import { FieldsForOperationProps, useFieldsForOperation } from './useFieldsForOperation';


export interface FieldsForResourceProps extends Omit<FieldsForOperationProps, 'operationId'>{
  record?: RaRecord | undefined
  resource?: string | undefined
}


const useFieldsForResource = (
  {
    record=undefined,
    resource=undefined,
    ...rest
  }: FieldsForResourceProps
): FieldDefinition[] => {
  
  const recordContext = useRecordContext(record);
  const resourceContext = useResourceContext({resource});
  const fieldDefinitions = useFieldsForOperation({
    operationId: recordContext === undefined ? `create_${resourceContext}` : `partial_update_${resourceContext}`,
    ...rest
  })
  
  return fieldDefinitions
} 


export default useFieldsForResource;