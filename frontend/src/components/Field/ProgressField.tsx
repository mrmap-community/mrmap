import { useMemo, type ReactNode } from 'react'

import Box from '@mui/material/Box'
import LinearProgress, { LinearProgressPropsColorOverrides, type LinearProgressProps } from '@mui/material/LinearProgress'
import Typography from '@mui/material/Typography'
import { OverridableStringUnion } from '@mui/types'
import { RaRecord, useFieldValue, useRecordContext } from 'react-admin'


export interface ProgressFieldProps extends LinearProgressProps {
  source: string
  getColor?: (record: RaRecord) => OverridableStringUnion<'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' | 'inherit', LinearProgressPropsColorOverrides>;
}


const ProgressField = (
  {
    getColor,
    ...props
  }: ProgressFieldProps
): ReactNode => {


  const value = useFieldValue(props);
  const progressValue = Number(value || 0)
  const record = useRecordContext();
  
  const color = useMemo(()=> {
    if (record !== undefined){
      return (getColor && getColor(record)) ?? 'info'
    }
    return 'info'
  },[record])

  return (
    <Box sx={{ display: 'flex', alignItems: 'center' }}>
      <Box sx={{ width: '100%', mr: 1 }}>
        <LinearProgress 
          variant="determinate" 
          value={value || 0}
          color={color}
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