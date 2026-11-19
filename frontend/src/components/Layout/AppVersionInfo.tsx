import { useTranslate } from 'react-admin';

import WarningAmberOutlinedIcon from '@mui/icons-material/WarningAmberOutlined';
import { Box, Tooltip, Typography } from '@mui/material';

import { backendVersionMismatch, displayVersion, isDevelopmentRevision } from './appVersion';

interface AppVersionInfoProps {
    // the version the backend's OpenAPI document answers (MrMap.VERSION on
    // the server, i.e. the same canonical file); unknown while loading
    backendVersion?: string | null;
}

// The About display of the footer (#1579). It shows the frontend's own
// version - the canonical VERSION file injected at build time - and names the
// skew when the backend answers a different one, which is what an operator
// comparing "the page I look at" against "the API I call" needs to see. An
// unstamped build (no MRMAP_BUILD_REVISION) is marked as a development
// revision instead of pretending to be an exact build. The tooltip carries
// both versions and mirrors into the accessible name; `SystemStatusIndicator`
// beside it is the pattern this follows (icon + label + aria-label).
const AppVersionInfo = ({ backendVersion }: AppVersionInfoProps) => {
    const translate = useTranslate();
    const version = displayVersion();
    const mismatch = backendVersionMismatch(backendVersion);
    const isDev = isDevelopmentRevision();

    const description = mismatch
        ? translate('footer.versionMismatch', {
            frontend: `v${version}`,
            backend: `v${(backendVersion ?? '').trim()}`,
        })
        : translate('footer.appVersion', { version: `v${version}` });

    return (
        <Tooltip title={description}>
            <Box
              component="span"
              aria-label={description}
              sx={{ alignItems: 'center', display: 'inline-flex', gap: 0.5, pl: 2 }}
            >
                <Typography component="span" variant="body2">
                    {`v${version}`}
                    {isDev ? ` (${translate('footer.devRevision')})` : ''}
                </Typography>
                {mismatch && (
                    <WarningAmberOutlinedIcon color="warning" fontSize="small" aria-hidden />
                )}
            </Box>
        </Tooltip>
    );
};

export default AppVersionInfo;
