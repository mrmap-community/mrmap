import { ReactNode } from "react"
import { useTranslate, WrapperField } from "react-admin"
import ListGuesser, { ListGuesserProps } from "../../../jsonapi/components/ListGuesser"
import EditDialogButton from "../../Dialog/EditDialogButton"
import ListActions, { CustomListActionsProps } from "../../Lists/CustomListActions"
import AllowedWebMapServiceOperationFields from "./AllowedWebMapServiceOperationFields"
import CreateAllowedWebMapServiceOperationDialogButton from "./CreateDialogButton"


const ListActionsAllowedWebMapServiceOperation = (
  { 
    ...props
  }: CustomListActionsProps
): ReactNode => {
  return (
    <ListActions
      createButton={<CreateAllowedWebMapServiceOperationDialogButton/>}
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