import { ResourceContext, useRecordContext } from 'react-admin';
import ListWithDialogs from '../../../../../jsonapi/components/ListWithDialogs';


export const UpdateJobTab = () => {
  const record = useRecordContext()
  return (
    <ResourceContext
      value='WebMapServiceUpdateJob'
    >
      <ListWithDialogs
        createGuesserProps={
          {
            resource: "WebMapServiceUpdateJob",
            defaultValues:{
              service: record
            },
          }
        }
      />
    </ResourceContext>
  )
}

export default UpdateJobTab