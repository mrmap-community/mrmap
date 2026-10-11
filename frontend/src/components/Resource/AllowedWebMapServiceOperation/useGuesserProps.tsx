import { useMemo } from 'react';
import { useRecordContext } from 'react-admin';
import useAllowedWebMapServiceOperationFieldDefinitions from './useAllowedWebMapServiceOperationFieldDefinitions';


const useGuesserProps = () => {
  const record = useRecordContext()

  const fieldDefinitions = useAllowedWebMapServiceOperationFieldDefinitions()
  const guesserProps = useMemo(()=> ({
    resource: "AllowedWebMapServiceOperation",
    updateFieldDefinitions: fieldDefinitions,
    defaultValues:{
      securedService: record
    }
  }),[
    fieldDefinitions, record
  ])
  return guesserProps
}

export default useGuesserProps;