import SimpleCard from "../../MUI/SimpleCard";
import {
    Alert, Box,
    Chip, LinearProgress, Stack, Typography
} from '@mui/material';
import { useTranslate } from 'react-admin';
import { systemComponents, useSystemStatus, type SystemStatusRecord } from '../../../context/SystemStatusContext';

const label = (value?: string | null) => value ? new Date(value).toLocaleString() : '—';
const color = (status: string): 'success' | 'error' | 'warning' | 'default' => {
    if (status === 'healthy') return 'success';
    if (['down'].includes(status)) return 'error';
    if (['degraded'].includes(status)) return 'warning';
    return 'default';
};

export const SystemStatusPanel = ({ data, stale }: { data: SystemStatusRecord; stale: boolean }) => {
    const translate = useTranslate();
    const t = (key: string) => translate(`systemStatus.${key}`);
    return (
        <SimpleCard cardProps={{ sx: {} }}>
            <Stack direction="row" sx={{ mb: 2, justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 1 }}>
                <Typography variant="h6">{t('title')}</Typography>
                <Typography variant="body2">{t('observed')}: {label(data.observedAt)}</Typography>
            </Stack>
            {stale && <Alert severity="warning" sx={{ mb: 2 }}>{t('stale')}</Alert>}
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', lg: 'repeat(4, 1fr)' }, gap: 2 }}>
                {systemComponents.map(name => {
                    const component = data.components[name];
                    const status = stale ? 'unknown' : component?.status ?? 'unknown';
                    return <Box key={name} sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 2 }}>
                        <Typography sx={{ mb: 1 }}>{t(name)}</Typography>
                        <Chip size="small" label={t(`states.${status}`)} color={color(status)} />
                        <Typography variant="body2" sx={{ mt: 1 }}>{stale ? t('noObservation') : component?.detail}</Typography>
                        {!stale && component?.last_seen && <Typography variant="caption">{t('lastSeen')}: {label(component.last_seen)}</Typography>}
                    </Box>;
                })}
            </Box>
        </SimpleCard>
    );
};

const SystemStatus = () => {
    const translate = useTranslate();
    const { data, isPending, forbidden, stale } = useSystemStatus();
    if (forbidden) return null;
    if (isPending) return <LinearProgress aria-label={translate('systemStatus.title')} />;
    if (!data) return <Alert severity="warning" sx={{ mb: 2 }}>{translate('systemStatus.unavailable')}</Alert>;
    return <SystemStatusPanel data={data} stale={stale} />;
};

export default SystemStatus;
