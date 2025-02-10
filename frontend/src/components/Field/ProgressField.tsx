import { useMemo, type ReactNode } from 'react'

import Box from '@mui/material/Box'
import LinearProgress, { type LinearProgressProps } from '@mui/material/LinearProgress'
import Typography from '@mui/material/Typography'
import { RaRecord, useRecordContext } from 'react-admin'


export interface ProgressFieldProps extends LinearProgressProps {
  source: string
  getColor?: (record: RaRecord) => void
}


const ProgressField = ({
  source,
  getColor,
  ...rest
}: ProgressFieldProps): ReactNode => {
  const record = useRecordContext();

  const props = useMemo(()=> ({
    ...rest, 
    ...(record && getColor && {color: getColor(record)})
  }), [rest, getColor, record])

  const value = useMemo(()=> (Number(record?.[source]) || 0), [record?.[source]])

  return (
    <Box sx={{ display: 'flex', alignItems: 'center' }}>
      <Box sx={{ width: '100%', mr: 1 }}>
        <LinearProgress 
          variant="determinate" 
          value={value}
          {...props} 
        />
      </Box>
      <Box sx={{ minWidth: 40 }}>
        <Typography variant="body2" color="text.secondary">{`${value?.toFixed(2)}%`}</Typography>
      </Box>
    </Box>
  )
}

export default ProgressField