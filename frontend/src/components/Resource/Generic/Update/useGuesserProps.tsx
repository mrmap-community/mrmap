import { useMemo } from 'react';
import { useRecordContext, useResourceContext } from 'react-admin';

import useMonitoringUpdateFieldDefinitions from './useUpdateSettingFieldDefinitions';



const useGuesserProps = () => {
  const record = useRecordContext()
  const resource = useResourceContext()
  const fieldDefinitions = useMonitoringUpdateFieldDefinitions()
  const guesserProps = useMemo(()=> ({
    resource: resource,
    updateFieldDefinitions: fieldDefinitions,
    defaultValues:{
      service: record
    },
  }),[
    fieldDefinitions, record
  ])
  return guesserProps
}

export default useGuesserProps;