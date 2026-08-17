import { ReactNode } from "react"
import { ExportButton, FilterButton, ListActionsProps, SelectColumnsButton, TopToolbar, useResourceDefinition } from "react-admin"
import CreateDialogButton from "../Dialog/CreateDialogButton"

export interface CustomListActionsProps extends Omit<Partial<ListActionsProps>, "filters"> {
  isConfigureable?: boolean
  isExportable?: boolean
  createButton?: ReactNode
  preferenceKey?: string
  filters: ReactNode[]
  additionalActions?: ReactNode
}


const CustomListActions = (
  { 
    isConfigureable = true,
    isExportable = true,
    createButton,
    filters,
    preferenceKey,
    additionalActions
  }: CustomListActionsProps
): ReactNode => {
  const { hasCreate } = useResourceDefinition()

  return (
    <TopToolbar>
      {isConfigureable && <SelectColumnsButton preferenceKey={preferenceKey}/>}
      {filters && <FilterButton filters={filters}/>}
      {createButton ?? (hasCreate && <CreateDialogButton />)}
      {isExportable && <ExportButton />}
      {additionalActions}
    </TopToolbar>
  )
}


export default CustomListActions