import lodashGet from 'lodash/get';
import lodashTemplate from 'lodash/template';
import lodashTemplateSettings from 'lodash/templateSettings';
import { I18nProvider } from 'react-admin';
import germanMessages from '../i18n/de';
import en from "../i18n/en";

let messages = en;
let locale = 'en';
const locales = [{locale: 'en', name: 'english'}, {locale: 'de', name: 'deutsch'}]


lodashTemplateSettings.interpolate = /%{([\s\S]+?)}/g;

const i18nProvider: I18nProvider = {
  translate: (key: string, options?: any) => {
    const translation = lodashGet(messages, key, key) as string
    const compiled = lodashTemplate(translation)
    const result = compiled(options)
    return result
  },
  changeLocale: (newLocale: string) => {
      messages = (newLocale === 'de') ? germanMessages : en;
      locale = newLocale;
      return Promise.resolve();
  },
  getLocale: () => locale,
  getLocales: () => locales
};

export default i18nProvider;