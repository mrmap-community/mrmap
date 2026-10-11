import SimpleCard from "../../MUI/SimpleCard";
import { Alert, LinearProgress, Typography } from '@mui/material';
import {
    DateField,
    RecordContextProvider,
    SimpleShowLayout, TextField, useGetOne, useTranslate, type RaRecord
} from 'react-admin';

interface SystemInfoRecord extends RaRecord {
    mrmapRelease: string;
    djangoVersion: string;
    pythonVersion: string;
    postgresqlVersion: string | null;
    databaseName: string | null;
    databaseSize: string | null;
    celeryWorkerCount: number;
    redisUp: boolean;
    systemTime: string;
}

const SystemView = () => {
    const translate = useTranslate();
    const { data, error, isPending } = useGetOne<SystemInfoRecord>(
        'SystemInfo', { id: 'current' }, { retry: false },
    );

    if (isPending) return <LinearProgress aria-label={translate('systemInfo.title')} />;
    if (error || !data) return <Alert severity="warning" sx={{ mb: 2 }}>{translate('systemInfo.unavailable')}</Alert>;

    return (
        <SimpleCard cardProps={{ sx: {} }}>
            <Typography variant="h6">{translate('systemInfo.title')}</Typography>
            <RecordContextProvider value={data}>
                <SimpleShowLayout>
                    <TextField source="mrmapRelease" label="systemInfo.mrmapRelease" />
                    <TextField source="djangoVersion" label="systemInfo.djangoVersion" />
                    <TextField source="pythonVersion" label="systemInfo.pythonVersion" />
                    <TextField source="postgresqlVersion" label="systemInfo.postgresqlVersion" emptyText="—" />
                    <TextField source="databaseName" label="systemInfo.databaseName" emptyText="—" />
                    <TextField source="databaseSize" label="systemInfo.databaseSize" emptyText="—" />
                    <DateField source="systemTime" label="systemInfo.systemTime" showTime />
                </SimpleShowLayout>
            </RecordContextProvider>
        </SimpleCard>
    );
};

export default SystemView;
