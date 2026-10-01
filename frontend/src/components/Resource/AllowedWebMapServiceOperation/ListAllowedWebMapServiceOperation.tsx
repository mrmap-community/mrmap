import { useMemo } from "react"
import { useRecordContext } from "react-admin"
import ListWithDialogs, { ListWithDialogsProps } from "../../../jsonapi/components/ListWithDialogs"
import CustomListActions from "../../Lists/CustomListActions"
import MapViewerButton from "../WebMapService/Button/MapViewerButton"
import useGuesserProps from "./useGuesserProps"



const ListAllowedWebMapServiceOperation = (
  {
    ...props
  }: ListWithDialogsProps
) => {
  const record = useRecordContext()
  
  const guesserProps = useGuesserProps()

  const actions = useMemo(()=>(
    record ? 
    <CustomListActions
      additionalActions={
        <MapViewerButton 
          wmsRecord={undefined} 
          capabilititesUrl={record?.xmlBackupFileSecured}
        />
      }
    />: 
    undefined

  ),[record])

  return (
    <ListWithDialogs
      {...props}
      editGuesserProps={props.editGuesserProps ?? guesserProps}
      createGuesserProps={props.createGuesserProps ?? guesserProps}
      listGuesserProps={{
        actions: actions,
        defaultSelectedColumns:["allowedArea", "description", "allowedGroups", "operations"],
        ...props.listGuesserProps,
      }}
    />
  )


}

export default ListAllowedWebMapServiceOperation