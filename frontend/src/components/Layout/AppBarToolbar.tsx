import { LoadingIndicator, LocalesMenuButton, ToggleThemeButton, useLocales, useThemesContext } from "react-admin";

import { Stack } from "@mui/material";

import BackgroundActivityPanel from '../Resource/BackgroundProcess/BackgroundActivityPanel';
import AttentionIndicator from './AttentionIndicator';
import SystemStatusIndicator from './SystemStatusIndicator';

const AppBarToolbar = () => {
    const locales = useLocales();

    const { darkTheme } = useThemesContext();
    return (
        <Stack
            direction="row"       
        >
            <BackgroundActivityPanel />
            <SystemStatusIndicator />
            <AttentionIndicator />
            {locales && locales.length > 1 ? <LocalesMenuButton /> : null}
            {darkTheme && <ToggleThemeButton />}
            <LoadingIndicator />
        </Stack>
    );
};

export default AppBarToolbar;