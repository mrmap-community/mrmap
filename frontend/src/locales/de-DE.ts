import component from './de-DE/component';
import globalHeader from './de-DE/globalHeader';
import menu from './de-DE/menu';
import pages from './de-DE/pages';
import pwa from './de-DE/pwa';
import settingDrawer from './de-DE/settingDrawer';
import settings from './de-DE/settings';

export default {
  'navBar.lang': 'Sprachen',
  'layout.user.link.help': 'Hilfe',
  'layout.user.link.privacy': 'Datenschutz',
  'layout.user.link.terms': 'Nutzungsbedingungen',
  'app.copyright.produced': 'Mr. Map Gemeinschaft',
  ...globalHeader,
  ...menu,
  ...settingDrawer,
  ...settings,
  ...pwa,
  ...component,
  ...pages,
};
