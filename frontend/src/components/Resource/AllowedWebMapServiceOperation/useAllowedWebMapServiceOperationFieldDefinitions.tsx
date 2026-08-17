import { useMemo } from 'react';
import { useRecordContext, useResourceContext } from 'react-admin';
import { useFieldsForOperation } from '../../../jsonapi/hooks/useFieldsForOperation';
import TreeSelectInput from '../../Input/TreeSelectInput';



const useAllowedWebMapServiceOperationFieldDefinitions = () => {
  const record = useRecordContext();
  const resource = useResourceContext({resource: "AllowedWebMapServiceOperation"});
  const fieldDefinitions = useFieldsForOperation(record === undefined ? `create_${resource}` : `partial_update_${resource}` )
    
  // Dynamic change depending fields
  const customFieldDefinitions = useMemo(()=>(
    fieldDefinitions
    .filter(def => def.props.disabled === false)
    .map(def => {
      if (def.props.source === 'securedLayers') {
        const newDef = {...def}
  
        newDef.component = TreeSelectInput
        newDef.props.dependingFieldName = "securedService"
        newDef.props.helperText = newDef.props.helperText ?? 'select the subtree(s) you want to secure'
        return newDef
      }
      
      return def
    })
  ),[fieldDefinitions])
  
  return customFieldDefinitions.map(
    (fieldDefinitions) => 
        ({
          component: fieldDefinitions.component, 
          props: { key: fieldDefinitions.props.source, ...fieldDefinitions.props}
        })
    )
} 


export default useAllowedWebMapServiceOperationFieldDefinitions;