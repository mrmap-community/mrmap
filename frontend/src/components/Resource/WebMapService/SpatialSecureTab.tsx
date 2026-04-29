import ListAllowedWebMapServiceOperation from '../AllowedWebMapServiceOperation/ListAllowedWebMapServiceOperation';

const AllowedWebMapServiceOperationOverview = () => {

  return (
      <ListAllowedWebMapServiceOperation 
        resource='AllowedWebMapServiceOperation'
        relatedResource='WebMapService'
        defaultSelectedColumns={["allowedArea", "description", "allowedGroups", "operations"]}
      />
  )
}


export const SpatialSecureTab = () => {
  return (
    <AllowedWebMapServiceOperationOverview />          
  )
}



export default SpatialSecureTab