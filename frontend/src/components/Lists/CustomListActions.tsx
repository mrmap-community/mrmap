import { ReactNode } from "react"
import { CanAccess, CreateButton, ExportButton, FilterButton, ListActionsProps, SelectColumnsButton, TopToolbar, useResourceContext, useResourceDefinition } from "react-admin"

export interface CustomListActionsProps extends Omit<Partial<ListActionsProps>, "filters"> {
  isConfigureable?: boolean
  isExportable?: boolean
  createButton?: ReactNode
  preferenceKey?: string
  additionalActions?: ReactNode
}


const CustomListActions = (
  { 
    isConfigureable = true,
    isExportable = true,
    createButton,
    preferenceKey,
    additionalActions,
  }: CustomListActionsProps
): ReactNode => {
  const {hasCreate} = useResourceDefinition()
  const resource = useResourceContext()
  
  return (
    <TopToolbar>
      {isConfigureable && <SelectColumnsButton preferenceKey={preferenceKey}/>}
      {<FilterButton />}
      {/* CreateButton and EditButton gate themselves on canAccess; the export
          of a list is a copy of its records and react-admin's ExportButton asks
          nothing, so #833's table decides it stays out of an anonymous screen */}
      {createButton ?? hasCreate ? <CreateButton />: null}
      {isExportable && resource !== undefined ? (
        <CanAccess action="export" resource={resource}>
          <ExportButton />
        </CanAccess>
      ) : null}
      {additionalActions}
      
    </TopToolbar>
  )
}


export default CustomListActions