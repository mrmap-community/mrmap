import { ReactNode } from "react"
import { useRecordContext, useTranslate, WrapperField } from "react-admin"
import ListGuesser, { ListGuesserProps } from "../../../jsonapi/components/ListGuesser"
import EditDialogButton from "../../Dialog/EditDialogButton"
import ListActions, { CustomListActionsProps } from "../../Lists/CustomListActions"
import MapViewerButton from "../WebMapService/MapViewerButton"
import AllowedWebMapServiceOperationFields from "./AllowedWebMapServiceOperationFields"
import CreateAllowedWebMapServiceOperationDialogButton from "./CreateDialogButton"

const ListActionsAllowedWebMapServiceOperation = (
  { 
    ...props
  }: CustomListActionsProps
): ReactNode => {
  // TODO: find a way to get the record from the list context, not from the show context, because this is used in a list and not in a show view
  //const { record } = useShowContext();
  const record = useRecordContext()
  return (
    <ListActions
      createButton={<CreateAllowedWebMapServiceOperationDialogButton/>}
      additionalActions={
        <MapViewerButton 
          wmsRecord={undefined} 
          //capabilititesUrl={record.xmlBackupFileSecured}
        />
      }
      {...props}
    />
  )
}

const RowActions = () => {
  const translate = useTranslate();
  return (
    <WrapperField label={translate("ra.list.actions")} >
        <EditDialogButton editDialogProps={{fieldComponent: <AllowedWebMapServiceOperationFields/>}}/>
    </WrapperField >
  )
}


const ListAllowedWebMapServiceOperation = (
  {
    ...props
  }: ListGuesserProps
) => {


  return (
    <ListGuesser
      ActionsComponent={ListActionsAllowedWebMapServiceOperation}
      rowActions={<RowActions/>}
      {...props}
    />
  )

}

export default ListAllowedWebMapServiceOperation