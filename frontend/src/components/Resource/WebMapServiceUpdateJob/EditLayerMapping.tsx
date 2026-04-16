import { RaRecord, useRecordContext } from 'react-admin';

import { useMemo } from 'react';
import EditGuesser from '../../../jsonapi/components/EditGuesser';
import { useFieldsForOperation } from '../../../jsonapi/hooks/useFieldsForOperation';



export interface EditLayerMappingProps {
    selectedMapping: RaRecord | undefined;
}

export const EditLayerMapping = (
  {
    selectedMapping
  }: EditLayerMappingProps
) => {

  const contextRecord = useRecordContext()
  
  console.log(contextRecord, 'contextRecord in EditLayerMapping')
  const fieldDefinitions = useFieldsForOperation(`partial_update_LayerMapping`)
  

  const updateFieldDefinitions = useMemo(()=>{
    const _updateFieldDefinitions: any[] = [...fieldDefinitions]
    
    const jobField = _updateFieldDefinitions.find(def => def.props.source === 'job');
    if (jobField) {
      jobField.props.sx = { ...jobField.props?.sx, display: 'none' };
    }

    const oldLayerField = _updateFieldDefinitions.find(def => def.props.source === 'oldLayer');
    if (oldLayerField) {
      oldLayerField.props.relatedResource = {
        resource: "WebMapService",
        id: contextRecord?.service?.id
      }
      oldLayerField.props.initialFilter = {
        'hasReverseMapping': false
      }
    }

    return _updateFieldDefinitions;
  },[fieldDefinitions])


  if (!selectedMapping) {
    return null;
  }
  return (
    <EditGuesser
        resource="LayerMapping"
        id={selectedMapping?.id}
        redirect={false}
        updateFieldDefinitions={updateFieldDefinitions}
    />
  )
}