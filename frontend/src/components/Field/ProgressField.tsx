import { useMemo, type ReactNode } from 'react'
import { RaRecord, useFieldValue, useRecordContext } from 'react-admin'

import Box from '@mui/material/Box'
import LinearProgress, { LinearProgressPropsColorOverrides, type LinearProgressProps } from '@mui/material/LinearProgress'
import Typography from '@mui/material/Typography'
import { OverridableStringUnion } from '@mui/types'


export interface ProgressFieldProps extends Omit<LinearProgressProps, 'variant'> {
  source: string
  getColor?: (record: RaRecord) => OverridableStringUnion<'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' | 'inherit', LinearProgressPropsColorOverrides>;
  /** renders a moving bar without a value for work whose total is unknown -
   *  no percentage may be invented for a process which does not know its
   *  denominator (#1207) */
  indeterminate?: boolean
}


const ProgressField = (
  {
    getColor,
    indeterminate = false,
    source,
    ...linearProps
  }: ProgressFieldProps
): ReactNode => {


  const value = useFieldValue({ source });
  const progressValue = Number(value || 0)
  const record = useRecordContext();
  
  const color = useMemo(()=> {
    if (record !== undefined){
      return (getColor && getColor(record)) ?? 'info'
    }
    return 'info'
  },[record])

  if (indeterminate) {
    return (
      <LinearProgress
        variant="indeterminate"
        color={color}
        {...linearProps}
      />
    )
  }

  return (
    <Box sx={{ display: 'flex', alignItems: 'center' }}>
      <Box sx={{ width: '100%', mr: 1 }}>
        <LinearProgress 
          variant="determinate" 
          value={value || 0}
          color={color}
          {...linearProps} 
          
        />
      </Box>
      <Box sx={{ minWidth: 40 }}>
        <Typography variant="body2" color="text.secondary">{`${progressValue?.toFixed(2)}%`}</Typography>
      </Box>
    </Box>
  )
}

export default ProgressField