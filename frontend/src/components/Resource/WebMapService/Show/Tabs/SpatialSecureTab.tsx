import { ResourceContext, useRecordContext } from 'react-admin';
import ListAllowedWebMapServiceOperation from '../../../AllowedWebMapServiceOperation/ListAllowedWebMapServiceOperation';


export const SpatialSecureTab = () => {
  const record = useRecordContext();
  return (
    <ResourceContext
      value='AllowedWebMapServiceOperation'
    >
      <ListAllowedWebMapServiceOperation listGuesserProps={{ relatedResource: { resource: "WebMapService", id: record?.id }, disableSyncWithLocation: true }} />
    </ResourceContext>
  )
}

export default SpatialSecureTab
