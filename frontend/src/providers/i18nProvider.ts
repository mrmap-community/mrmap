import lodashGet from 'lodash/get';
import lodashTemplate from 'lodash/template';
import lodashTemplateSettings from 'lodash/templateSettings';
import { I18nProvider } from 'react-admin';
import germanMessages from '../i18n/de';
import en from "../i18n/en";

export const LOCALE_STORAGE_NAME = "RaStore.locale"

let messages = en;
const locales = [{locale: 'en', name: 'english'}, {locale: 'de', name: 'deutsch'}]


lodashTemplateSettings.interpolate = /%{([\s\S]+?)}/g;

const i18nProvider: I18nProvider = {
  translate: (key: string, options?: any) => {
    // Try to fetch the translation. If missing, lodashGet returns the key.
    let translation = lodashGet(messages, key, key) as string;

    // If the key is missing and a fallback message is provided in options ("_"), use it
    if (translation === key && options && options._) {
      translation = options._;
    }

    // Handle simple pluralization using the "||||" separator used by react-admin
    // We support two forms: singular |||| plural
    let message = translation;
    if (typeof message === 'string' && message.indexOf('||||') !== -1) {
      const parts = message.split('||||').map((s) => s.trim());
      const count = options?.smart_count ?? options?.count ?? options?.smartCount;
      const usePlural = typeof count === 'number' ? count !== 1 : false;
      message = parts[usePlural ? 1 : 0] ?? parts[0];
    }

    const compiled = lodashTemplate(message);
    const result = compiled(options);
    return result;
  },
  changeLocale: (newLocale: string) => {
      messages = (newLocale === 'de') ? germanMessages : en;
      localStorage.setItem(LOCALE_STORAGE_NAME, newLocale)
      return Promise.resolve();
  },
  getLocale: () => localStorage.getItem(LOCALE_STORAGE_NAME) ?? 'en',
  getLocales: () => locales
};

export default i18nProvider;