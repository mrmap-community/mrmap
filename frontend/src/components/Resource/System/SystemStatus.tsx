import {
    Alert, Box,
    Card, CardContent, Chip, LinearProgress, Stack, Typography
} from '@mui/material';
import { useEffect, useState } from 'react';
import {
    useGetOne, useTranslate,
    type RaRecord,
} from 'react-admin';

interface Observation {
    status: string;
    detail: string;
    last_seen?: string | null;
}
interface SystemStatusRecord extends RaRecord {
    observedAt: string | null;
    stale: boolean;
    staleAfter: number;
    components: Record<string, Observation>;

}

const label = (value?: string | null) => value ? new Date(value).toLocaleString() : '—';
const color = (status: string): 'success' | 'error' | 'warning' | 'default' => {
    if (status === 'healthy') return 'success';
    if (['down'].includes(status)) return 'error';
    if (['degraded'].includes(status)) return 'warning';
    return 'default';
};

export const SystemStatusPanel = ({ data, failed = false }: { data: SystemStatusRecord; failed?: boolean }) => {
    const translate = useTranslate();
    const t = (key: string) => translate(`systemStatus.${key}`);
    const [clock, setClock] = useState(Date.now());
    useEffect(() => {
        const timer = window.setInterval(() => setClock(Date.now()), 5000);
        return () => window.clearInterval(timer);
    }, []);
    const stale = failed || data.stale || !data.observedAt ||
        clock - Date.parse(data.observedAt) > data.staleAfter * 1000;
    return (
        <Card>
            <CardContent>
                <Stack direction="row" sx={{ mb: 2, justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 1 }}>
                    <Typography variant="h6">{t('title')}</Typography>
                    <Typography variant="body2">{t('observed')}: {label(data.observedAt)}</Typography>
                </Stack>
                {stale && <Alert severity="warning" sx={{ mb: 2 }}>{t('stale')}</Alert>}
                <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', lg: 'repeat(4, 1fr)' }, gap: 2 }}>
                    {['workers', 'beat', 'redis', 'database'].map(name => {
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
            </CardContent>
        </Card>
    );
};

const SystemStatus = () => {
    const translate = useTranslate();
    const { data, error, isPending } = useGetOne<SystemStatusRecord>(
        'SystemStatus', { id: 'current' },
        {
            refetchInterval: query => {
                const error = query.state.error as { response?: { status?: number }; status?: number } | null;
                const status = error?.response?.status ?? error?.status;
                return status === 401 || status === 403 ? false : 15000;
            },
            refetchIntervalInBackground: true, retry: false,
        },
    );
    // The endpoint enforces staff access. Non-staff dashboards simply omit this panel.
    const status = (error as { status?: number; response?: { status?: number } } | null)?.response?.status ??
        (error as { status?: number } | null)?.status;
    if (status === 403 || status === 401) return null;
    if (isPending) return <LinearProgress aria-label={translate('systemStatus.title')} />;
    if (!data) return <Alert severity="warning" sx={{ mb: 2 }}>{translate('systemStatus.unavailable')}</Alert>;
    return <SystemStatusPanel data={data} failed={!!error} />;
};

export default SystemStatus;
