import { useMemo } from 'react';
import { useRecordContext, useResourceContext } from 'react-admin';

import SchedulePreviewPanel from '../Schedule/SchedulePreviewPanel';
import useMonitoringUpdateFieldDefinitions from './useUpdateSettingFieldDefinitions';



const useGuesserProps = () => {
  const record = useRecordContext()
  const resource = useResourceContext()
  const fieldDefinitions = useMonitoringUpdateFieldDefinitions()
  // the service kind comes from the schema reference of the settings'
  // service field, not from a hardcoded name table (#1327)
  const serviceKind = fieldDefinitions.find(
    fieldDefinition =>
      fieldDefinition.props.source === 'service' &&
      fieldDefinition.props.reference !== undefined
  )?.props.reference
  const guesserProps = useMemo(()=> ({
    resource: resource,
    updateFieldDefinitions: fieldDefinitions,
    defaultValues:{
      service: record
    },
    referenceInputs: [
      <SchedulePreviewPanel
        key='schedule-preview'
        operation='update'
        serviceKind={serviceKind}
        serviceId={record?.id}
      />
    ],
  }),[
    resource, fieldDefinitions, record, serviceKind
  ])
  return guesserProps
}

export default useGuesserProps;