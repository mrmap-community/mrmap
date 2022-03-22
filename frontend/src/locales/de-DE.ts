import component from './de-DE/component';
import globalHeader from './de-DE/globalHeader';
import menu from './de-DE/menu';
import pages from './de-DE/pages';
import pwa from './de-DE/pwa';
import settingDrawer from './de-DE/settingDrawer';
import settings from './de-DE/settings';

export default {
  'navBar.lang': 'Languages',
  'layout.user.link.help': 'Help',
  'layout.user.link.privacy': 'Privacy',
  'layout.user.link.terms': 'Terms',
  'app.copyright.produced': 'Produced by mrmap community',
  'app.preview.down.block': 'Download this page to your local project',
  'app.welcome.link.fetch-blocks': 'Get all block',
  'app.welcome.link.block-list': 'Quickly build standard, pages based on `block` development',
  ...globalHeader,
  ...menu,
  ...settingDrawer,
  ...settings,
  ...pwa,
  ...component,
  ...pages,
};
