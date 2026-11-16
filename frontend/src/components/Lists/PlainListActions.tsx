import type { ReactNode } from "react"

import CustomListActions, { type CustomListActionsProps } from "./CustomListActions"

/**
 * The actions of a list embedded in another screen: no column chooser and no
 * export, which belong to a list the user owns. CustomListActions was the
 * alternative considered and is exactly what this configures — the four
 * embedded lists that used to spell this combination out in an inline arrow
 * now share one definition.
 */
const PlainListActions = (props: CustomListActionsProps): ReactNode => (
  <CustomListActions {...props} isConfigureable={false} isExportable={false} />
)

export default PlainListActions
