import { RaRecord, useRecordContext } from 'react-admin';

import { useMemo } from 'react';
import EditGuesser, { EditGuesserProps } from '../../../jsonapi/components/EditGuesser';
import { useFieldsForOperation } from '../../../jsonapi/hooks/useFieldsForOperation';
import { useQueryParam } from '../../utils';


export const EditLayerMapping = (
  {
    ...rest
  }: EditGuesserProps
) => {
  const [selectedLayer] = useQueryParam('selectedLayer');

  const contextRecord = useRecordContext()
  
  const fieldDefinitions = useFieldsForOperation(`partial_update_LayerMapping`)
  
  const mappings = useMemo(() => contextRecord?.mappings || [], [contextRecord?.mappings])

  const selectedMapping = useMemo<RaRecord | undefined>(() => 
      mappings.find((m: RaRecord) => m.newLayer?.id === selectedLayer),
      [mappings, selectedLayer]
  );
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
        {...rest}
    />
  )
}