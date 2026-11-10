import { LoadingIndicator, LocalesMenuButton, ToggleThemeButton, useLocales, useThemesContext } from "react-admin";

import { Stack } from "@mui/material";

import JobCenterIndicator from '../Resource/BackgroundProcess/JobCenter/JobCenterIndicator';
import AttentionIndicator from './AttentionIndicator';
import SystemStatusIndicator from './SystemStatusIndicator';

const AppBarToolbar = () => {
    const locales = useLocales();

    const { darkTheme } = useThemesContext();
    return (
        <Stack
            direction="row"       
        >
            <JobCenterIndicator />
            <SystemStatusIndicator />
            <AttentionIndicator />
            {locales && locales.length > 1 ? <LocalesMenuButton /> : null}
            {darkTheme && <ToggleThemeButton />}
            <LoadingIndicator />
        </Stack>
    );
};

export default AppBarToolbar;