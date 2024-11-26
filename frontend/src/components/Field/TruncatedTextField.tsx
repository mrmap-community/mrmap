import { type ReactElement } from 'react'
import { TextField, TextFieldProps } from 'react-admin'

import Typography from '@mui/material/Typography'
import {
  useFieldValue
} from 'ra-core'

import MouseOverPopover from './MouseOverPopover'

export interface ReferenceManyCountProps {
  resource: string
  relatedType: string
  source: string
}

const TruncatedTextField = (
  {
    ...rest
  }: TextFieldProps
): ReactElement => {
  const value = useFieldValue(rest);

  if (value?.length > 100) {
    return (
    <div>
      <Typography>{value.slice(0, 100)}</Typography>
      <MouseOverPopover
        content={value}
      >
        <span>...</span>
      </MouseOverPopover>
    </div>
   
  )
  } else {
    return <TextField {...rest} />
  }
   
}


export default TruncatedTextField