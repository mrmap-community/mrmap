import { LoadingIndicator, LocalesMenuButton, ToggleThemeButton, useLocales, useThemesContext } from "react-admin";
import SearchForm from "../Search/SearchForm";

const AppBarToolbar = () => {
    const locales = useLocales();

    const { darkTheme } = useThemesContext();
    return (
        <>
            <SearchForm/>
            {locales && locales.length > 1 ? <LocalesMenuButton /> : null}
            {darkTheme && <ToggleThemeButton />}
            <LoadingIndicator />
        </>
    );
};

export default AppBarToolbar;