import { useRecordContext } from "react-admin"
import ListWithDialogs, { ListWithDialogsProps } from "../../../jsonapi/components/ListWithDialogs"
import CustomListActions from "../../Lists/CustomListActions"
import MapViewerButton from "../WebMapService/MapViewerButton"
import useGuesserProps from "./useGuesserProps"



const ListAllowedWebMapServiceOperation = (
  {
    ...props
  }: ListWithDialogsProps
) => {
  const record = useRecordContext()
  const guesserProps = useGuesserProps()

  return (
    <ListWithDialogs
      editGuesserProps={guesserProps}
      createGuesserProps={guesserProps}
      listGuesserProps={{
        actions: <CustomListActions
          additionalActions={
            <MapViewerButton 
          wmsRecord={undefined} 
          capabilititesUrl={record?.xmlBackupFileSecured}
        />
          }
        />,
        defaultSelectedColumns:["allowedArea", "description", "allowedGroups", "operations"],
        
      }}
      {...props}
    />
  )


}

export default ListAllowedWebMapServiceOperation