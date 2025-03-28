import { Card, CardProps } from '@mui/material';
import { useRef } from 'react';
import { useSidebarState } from 'react-admin';

export interface AsideCardProps extends CardProps {
}

const AsideCard = ({
  children,
  ...rest
}: AsideCardProps) => {
  const [open] = useSidebarState()
  const ref = useRef(null)
  
  return (
    <Card
      ref={ref}
      sx={{
        marginLeft: '1em',
        height: '100%', // 174px ==> 50 appbar, 52 pagination,  1 em top padding
        width: `calc(${open ? '40vw' : '20vw'} - 1em - ${open ? '240px' : '50px'})`,
        
      }}
      {...rest}
    >
      {children}
    </Card>
  )
}

export default AsideCard