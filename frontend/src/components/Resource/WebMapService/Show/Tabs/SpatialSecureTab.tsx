import { ResourceContext } from 'react-admin';
import ListAllowedWebMapServiceOperation from '../../../AllowedWebMapServiceOperation/ListAllowedWebMapServiceOperation';


export const SpatialSecureTab = () => {
  return (
    <ResourceContext
      value='AllowedWebMapServiceOperation'
    >
      <ListAllowedWebMapServiceOperation/>       
    </ResourceContext>
  )
}

export default SpatialSecureTab