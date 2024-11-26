import { LoadingIndicator, LocalesMenuButton, ToggleThemeButton, useLocales, useThemesContext } from "react-admin";

const AppBarToolbar = () => {
    const locales = useLocales();
    const { darkTheme } = useThemesContext();
    return (
        <>
            {locales && locales.length > 1 ? <LocalesMenuButton /> : null}
            {darkTheme && <ToggleThemeButton />}
            <LoadingIndicator />
        </>
    );
};

export default AppBarToolbar;