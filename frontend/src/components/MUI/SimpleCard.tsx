import { Card, CardContent, CardHeader, CardProps, Divider } from '@mui/material';
import { PropsWithChildren, ReactNode } from 'react';


export interface SimpleCardProps extends PropsWithChildren {
  title?: ReactNode
  subheader?: ReactNode
  cardProps?: CardProps
}

const SimpleCard = ({
  title,
  subheader,
  cardProps,
  children
  

}: SimpleCardProps) => {


  return (
    <Card
      sx={{boxShadow: 4, height: '100%'}}
      {...cardProps}
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