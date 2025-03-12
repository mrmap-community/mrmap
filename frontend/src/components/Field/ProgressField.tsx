import { type ReactNode } from 'react'

import Box from '@mui/material/Box'
import LinearProgress, { type LinearProgressProps } from '@mui/material/LinearProgress'
import Typography from '@mui/material/Typography'
import { RaRecord, useFieldValue } from 'react-admin'


export interface ProgressFieldProps extends LinearProgressProps {
  source: string
  getColor?: (record: RaRecord) => void
}


const ProgressField = (
  props: ProgressFieldProps
): ReactNode => {

  const {
    source,
    getColor,
    ...rest
  } = props;

  const value = useFieldValue(props);
  const progressValue = Number(value || 0)

  return (
    <Box sx={{ display: 'flex', alignItems: 'center' }}>
      <Box sx={{ width: '100%', mr: 1 }}>
        <LinearProgress 
          variant="determinate" 
          value={value || 0}
          {...props} 
          
        />
      </Box>
      <Box sx={{ minWidth: 40 }}>
        <Typography variant="body2" color="text.secondary">{`${progressValue?.toFixed(2)}%`}</Typography>
      </Box>
    </Box>
  )
}

export default ProgressField