import { ReactNode } from "react"
import { CreateButton, ExportButton, FilterButton, ListActionsProps, SelectColumnsButton, TopToolbar } from "react-admin"

export interface CustomListActionsProps extends Omit<Partial<ListActionsProps>, "filters"> {
  isConfigureable?: boolean
  isExportable?: boolean
  createButton?: ReactNode
  preferenceKey?: string
  filters?: ReactNode[]
  additionalActions?: ReactNode
}


const CustomListActions = (
  { 
    isConfigureable = true,
    isExportable = true,
    createButton,
    filters,
    preferenceKey,
    additionalActions,
  }: CustomListActionsProps
): ReactNode => {
  return (
    <TopToolbar>
      {isConfigureable && <SelectColumnsButton preferenceKey={preferenceKey}/>}
      {<FilterButton filters={filters}/>}
      {createButton ?? <CreateButton />}
      {isExportable && <ExportButton />}
      {additionalActions}
    </TopToolbar>
  )
}


export default CustomListActions