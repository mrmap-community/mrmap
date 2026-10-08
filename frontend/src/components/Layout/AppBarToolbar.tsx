import { Stack } from "@mui/material";
import { LoadingIndicator, LocalesMenuButton, ToggleThemeButton, useLocales, useThemesContext } from "react-admin";

import BackgroundActivityPanel from '../Resource/BackgroundProcess/BackgroundActivityPanel';

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
            {locales && locales.length > 1 ? <LocalesMenuButton /> : null}
            {darkTheme && <ToggleThemeButton />}
            <LoadingIndicator />
        </Stack>
    );
};

export default AppBarToolbar;