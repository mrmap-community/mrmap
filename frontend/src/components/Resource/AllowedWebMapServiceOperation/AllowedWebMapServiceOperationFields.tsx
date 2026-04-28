import { createElement, useMemo } from 'react';
import { useResourceContext } from 'react-admin';
import { useWatch } from "react-hook-form";
import { useParams } from 'react-router-dom';
import { useFieldsForOperation } from '../../../jsonapi/hooks/useFieldsForOperation';
import TreeSelectInput from '../../Input/TreeSelectInput';



const AllowedWebMapServiceOperationFields = () => {
  const { id } = useParams()

  const resource = useResourceContext()
  const securedServiceValue = useWatch({name: 'securedService'})
  const fieldDefinitions = useFieldsForOperation(id === undefined ? `create_${resource}` : `partial_update_${resource}` )

  // Dynamic change depending fields
  const customFieldDefinitions = useMemo(()=>(
    fieldDefinitions
    .filter(def => def.props.disabled === false)
    .map(def => {
      if (def.props.source === 'securedLayers') {
        const newDef = {...def}
        const wmsId = securedServiceValue?.id || undefined
        
        newDef.component = TreeSelectInput
        newDef.props.wmsId = wmsId
        newDef.props.helperText = wmsId === undefined ? 'select a service first': newDef.props.helperText ?? 'select the subtree(s) you want to secure'
        return newDef
      }
      return def
    })
  ),[fieldDefinitions, securedServiceValue])
  
  return customFieldDefinitions.map(
    (fieldDefinitions) => createElement(
        fieldDefinitions.component, { key: fieldDefinitions.props.source, ...fieldDefinitions.props}
      )
    )
} 


export default AllowedWebMapServiceOperationFields;