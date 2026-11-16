import { useCreatePath, useRedirect, useTranslate } from 'react-admin';

import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutlined';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlined';
import HelpOutlineIcon from '@mui/icons-material/HelpOutlined';
import WarningAmberIcon from '@mui/icons-material/WarningAmberOutlined';
import { Chip, Tooltip } from '@mui/material';

import { useSystemStatus } from '../../context/SystemStatusContext';

const SystemStatusIndicator = () => {
    const { health, isPending, forbidden } = useSystemStatus();
    const translate = useTranslate();
    const redirect = useRedirect();
    const createPath = useCreatePath();
    if (forbidden) return null;

    const stateKey = isPending ? 'checking' : `states.${health}`;
    const state = translate(`systemStatus.${stateKey}`);
    const label = `${translate('systemStatus.title')}: ${state}`;
    let icon = <HelpOutlineIcon />;
    if (health === 'healthy') icon = <CheckCircleOutlineIcon />;
    else if (health === 'down') icon = <ErrorOutlineIcon />;
    else if (health === 'degraded') icon = <WarningAmberIcon />;

    let color: 'success' | 'error' | 'warning' | 'default' = 'default';
    if (health === 'healthy') color = 'success';
    else if (health === 'down') color = 'error';
    else if (health === 'degraded') color = 'warning';

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
