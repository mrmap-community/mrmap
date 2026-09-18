import { ResourceContext, useRecordContext } from 'react-admin';
import ListWithDialogs from '../../../../../jsonapi/components/ListWithDialogs';


export const WebMapServiceOperationUrlsTab = () => {
  const record = useRecordContext();
  return (
    <ResourceContext
          value='WebMapServiceOperationUrl'
        >
      <ListWithDialogs
        listGuesserProps={{
          relatedResource: 'WebMapService',
          relatedResourceId: record?.id,
          defaultSelectedColumns:["operation", "url", "method"],
        }}
              />
      </ResourceContext>
  )
}

export default WebMapServiceOperationUrlsTab