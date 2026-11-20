import { LoadingIndicator, LocalesMenuButton, ToggleThemeButton, useAuthState, useLocales, useThemesContext } from "react-admin";

import { Stack } from "@mui/material";

import JobCenterIndicator from '../Resource/BackgroundProcess/JobCenter/JobCenterIndicator';
import IncidentCenterIndicator from '../Resource/OperationalIncident/IncidentCenter/IncidentCenterIndicator';
import AttentionIndicator from './AttentionIndicator';
import SystemStatusIndicator from './SystemStatusIndicator';

const AppBarToolbar = () => {
    const locales = useLocales();
    // #833: the indicators count operator data (jobs, system status, alerts,
    // incidents); their reads are gated behind the session, so their chips read
    // nothing for an anonymous visitor and are not rendered at all
    const { authenticated } = useAuthState();

    const { darkTheme } = useThemesContext();
    return (
        <Stack
            direction="row"       
        >
            {!!authenticated && <>
                <JobCenterIndicator />
                <SystemStatusIndicator />
                <AttentionIndicator />
                <IncidentCenterIndicator />
            </>}
            {locales && locales.length > 1 ? <LocalesMenuButton /> : null}
            {darkTheme && <ToggleThemeButton />}
            <LoadingIndicator />
        </Stack>
    );
};

export default AppBarToolbar;