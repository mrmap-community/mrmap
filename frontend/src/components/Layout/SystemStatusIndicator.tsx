import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutlined';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlined';
import HelpOutlineIcon from '@mui/icons-material/HelpOutlined';
import WarningAmberIcon from '@mui/icons-material/WarningAmberOutlined';
import { Chip, Tooltip } from '@mui/material';
import { useCreatePath, useRedirect, useTranslate } from 'react-admin';
import { useSystemStatus } from '../../context/SystemStatusContext';

const SystemStatusIndicator = () => {
    const { health, isPending, forbidden } = useSystemStatus();
    const translate = useTranslate();
    const redirect = useRedirect();
    const createPath = useCreatePath();
    if (forbidden) return null;

    const state = translate(`systemStatus.${isPending ? 'checking' : `states.${health}`}`);
    const label = `${translate('systemStatus.title')}: ${state}`;
    const icon = health === 'healthy' ? <CheckCircleOutlineIcon />
        : health === 'down' ? <ErrorOutlineIcon />
        : health === 'degraded' ? <WarningAmberIcon /> : <HelpOutlineIcon />;
    const color = health === 'healthy' ? 'success' : health === 'down' ? 'error'
        : health === 'degraded' ? 'warning' : 'default';

    return (
        <Tooltip title={`${label} — ${translate('systemStatus.viewDetails')}`}>
            <Chip
                component="button"
                type="button"
                clickable
                size="small"
                color={color}
                icon={icon}
                label={label}
                aria-label={label}
                onClick={() => redirect(createPath({ resource: 'SystemInfo', type: 'list' }))}
                sx={{
                    alignSelf: 'center',
                    mx: 1,
                    '& .MuiChip-label': { display: { xs: 'none', sm: 'block' } },
                    '& .MuiChip-icon': { mr: { xs: 0.5, sm: -0.75 } },
                }}
            />
        </Tooltip>
    );
};

export default SystemStatusIndicator;
