import { createElement, FC, ReactNode } from 'react';
import { Link, To } from 'react-router-dom';

import { Box, Card, Typography } from '@mui/material';
import { useListContext } from 'react-admin';
import HistoryChart from '../../Resource/Generic/History/HistoryChart';

interface Props {
    icon: FC<any>;
    to: To;
    title?: string;
    subtitle?: ReactNode;
    children?: ReactNode;
    resource?: string;
}

const CardWithIcon = ({ 
    icon, 
    title, 
    subtitle, 
    to,
    resource,
    children 
}: Props) => {
    const { total } = useListContext();

    return (
        <Card
            sx={{
                minHeight: 52,
                display: 'flex',
                flexDirection: 'column',
                flex: '1',
                '& a': {
                    textDecoration: 'none',
                    color: 'inherit',
                },
            }}
        >
            <Box
                sx={{
                    position: 'relative',
                    overflow: 'hidden',
                    //padding: '16px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    '& .icon': {
                        color: 'secondary.main',
                    },
                    '&:before': {
                        position: 'absolute',
                        top: '50%',
                        left: 0,
                        display: 'block',
                        content: `''`,
                        height: '200%',
                        aspectRatio: '1',
                        transform: 'translate(-30%, -60%)',
                        borderRadius: '50%',
                        backgroundColor: 'secondary.main',
                        opacity: 0.15,
                    },
                }}
            >
                <Box width="3em" className="icon" padding={'16px'}>
                    {icon === undefined ? null: createElement(icon, { fontSize: 'large' })}
                </Box>
                    <Link to={to}>
                        <Box textAlign="right" paddingRight={'16px'}>
                            <Typography color="textSecondary">{title}</Typography>
                            <Typography variant="h5" component="h2">
                                {subtitle || ' '}
                            </Typography>
                            
                        </Box>
                    </Link>
                
                    
            </Box>
            <HistoryChart height={100} total={total}/>
            {children}
        </Card>
    )
};

export default CardWithIcon;
