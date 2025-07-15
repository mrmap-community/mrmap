import { Card, CardContent, CardHeader, Divider } from '@mui/material';
import { PropsWithChildren, ReactNode } from 'react';


export interface SimpleCardProps extends PropsWithChildren {
  title?: ReactNode
  subheader?: ReactNode
}

const SimpleCard = ({
  title,
  subheader,
  children
}: SimpleCardProps) => {


  return (
    <Card
      sx={{boxShadow: 4, marginBottom: '1em'}}
    >
        <CardHeader 
          title={title} 
          subheader={subheader}/>
        <Divider />
        <CardContent>
            {children}
        </CardContent>
      </Card>
  )
};

export default SimpleCard;