import { ReactNode } from "react"
import { ExportButton, FilterButton, ListActionsProps, SelectColumnsButton, TopToolbar } from "react-admin"
import CreateDialogButton, { CreateDialogButtonProps } from "../Dialog/CreateDialogButton"

export interface CustomListActionsProps extends Omit<Partial<ListActionsProps>, "filters"> {
  isConfigureable?: boolean
  isExportable?: boolean
  createButton?: ReactNode
  preferenceKey?: string
  filters?: ReactNode[]
  additionalActions?: ReactNode
  dialogGuesserProps?: CreateDialogButtonProps
}


const CustomListActions = (
  { 
    isConfigureable = true,
    isExportable = true,
    createButton,
    filters,
    preferenceKey,
    additionalActions,
    dialogGuesserProps,
  }: CustomListActionsProps
): ReactNode => {
  return (
    <TopToolbar>
      {isConfigureable && <SelectColumnsButton preferenceKey={preferenceKey}/>}
      {<FilterButton filters={filters}/>}
      {createButton ?? <CreateDialogButton  {...dialogGuesserProps}/>}
      {isExportable && <ExportButton />}
      {additionalActions}
    </TopToolbar>
  )
}


export default CustomListActions