import { ReactNode } from "react"
import { useRecordContext, useTranslate, WrapperField } from "react-admin"
import ListGuesser, { ListGuesserProps } from "../../../jsonapi/components/ListGuesser"
import CreateDialogButton from "../../Dialog/CreateDialogButton"
import EditDialogButton from "../../Dialog/EditDialogButton"
import ListActions, { CustomListActionsProps } from "../../Lists/CustomListActions"
import EmptyList from "../../Lists/Empty"
import MapViewerButton from "../WebMapService/MapViewerButton"
import useAllowedWebMapServiceOperationFieldDefinitions from "./useAllowedWebMapServiceOperationFieldDefinitions"


const ListActionsAllowedWebMapServiceOperation = (
  { 
    ...props
  }: CustomListActionsProps
): ReactNode => {
  const record = useRecordContext()
  const fieldDefinitions = useAllowedWebMapServiceOperationFieldDefinitions()

  return (
    <ListActions
      createButton={
        <CreateDialogButton 
          createDialogProps={{
            updateFieldDefinitions: fieldDefinitions,
            formProps: { 
              defaultValues: {
                "securedService": record
              },
            }
          }}
          
        />
      }
      additionalActions={
        <MapViewerButton 
          wmsRecord={undefined} 
          capabilititesUrl={record?.xmlBackupFileSecured}
        />
      }
      {...props}
    />
  )
}

const RowActions = () => {
  const translate = useTranslate();
  const fieldDefinitions = useAllowedWebMapServiceOperationFieldDefinitions()

  return (
    <WrapperField label={translate("ra.list.actions")} >
        <EditDialogButton editDialogProps={{
          resource: "AllowedWebMapServiceOperation",
          updateFieldDefinitions: fieldDefinitions
        }}/>
    </WrapperField >
  )
}


const ListAllowedWebMapServiceOperation = (
  {
    ...props
  }: ListGuesserProps
) => {
  const record = useRecordContext()
  const fieldDefinitions = useAllowedWebMapServiceOperationFieldDefinitions()

  return (
    <ListGuesser
      ActionsComponent={ListActionsAllowedWebMapServiceOperation}
      empty={
        <EmptyList
          createDialogProps={{
            updateFieldDefinitions: fieldDefinitions,
            formProps: { 
              defaultValues: {
                "securedService": record
              },
            }
          }}
        />
      }
      rowActions={<RowActions/>}
      {...props}
    />
  )

}

export default ListAllowedWebMapServiceOperation