import { I18nProvider } from 'react-admin';

import lodashGet from 'lodash/get';

import germanMessages from '../i18n/de';
import en from "../i18n/en";

export const LOCALE_STORAGE_NAME = "RaStore.locale"

let messages: typeof en | typeof germanMessages = en;
const locales = [{locale: 'en', name: 'english'}, {locale: 'de', name: 'deutsch'}]

type TranslateOptions = Parameters<I18nProvider["translate"]>[1];

/** The token syntax of react-admin's catalogs: `%{name}`. */
const tokenPattern = /%\{([^{}]+)\}/g;

/**
 * Replace the `%{token}` placeholders of a message with the options of the same
 * name - one pass over the string, the way react-admin's own substitution is
 * done. A token the options do not carry is left written out, as react-admin
 * leaves it too, and a value is handed over as it is: the caller renders it
 * into a React node, which escapes it itself.
 *
 * The lodash template this replaces compiled a new function for every call of
 * the hottest function of a schema-guessed UI (#1465). It also answered an
 * unknown token from wherever the `with` scope of the compiled function found
 * that identifier: it threw for `smart_count`, silently answered `window.name`
 * for a `%{name}` without that option, and compiled a message which carried
 * lodash's own `<%` delimiters as code.
 */
const substituteTokens = (message: string, options?: TranslateOptions): string => {
  // The common call is a plain label: no options, no token, nothing to do.
  if (options === undefined || !message.includes("%{")) {
    return message;
  }

  return message.replace(tokenPattern, (placeholder: string, rawName: string) => {
    const name = rawName.trim();
    if (!Object.hasOwn(options, name)) {
      return placeholder;
    }
    const value = options[name];
    return value === undefined || value === null ? "" : String(value);
  });
};

const i18nProvider: I18nProvider = {
  translate: (key: string, options?: Parameters<I18nProvider["translate"]>[1]) => {
    // Try to fetch the translation. If missing, lodashGet returns the key.
    let translation = lodashGet(messages, key, key) as string;

    // If the key is missing and a fallback message is provided in options ("_"), use it
    if (translation === key && options?._) {
      translation = options._;
    }

    // Handle simple pluralization using the "||||" separator used by react-admin
    // We support two forms: singular |||| plural
    let message = translation;
    if (typeof message === 'string' && message.includes('||||')) {
      const parts = message.split('||||').map((s) => s.trim());
      const count = options?.smart_count ?? options?.count ?? options?.smartCount;
      const usePlural = typeof count === 'number' ? count !== 1 : false;
      message = parts[usePlural ? 1 : 0] ?? parts[0];
    }

    // A key which points at a whole branch of the catalog instead of a message
    // is stringified, as the template compiler stringified it before (#1465).
    return substituteTokens(String(message), options);
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