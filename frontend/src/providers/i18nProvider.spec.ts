/**
 * Pins what every label of the schema-driven UI reads through `translate`
 * (#1465). MrMap does not use react-admin's polyglot provider but its own one,
 * so the `%{token}` substitution, the `||||` plural forms react-admin's
 * catalogs are written with, and the "_" fallback for an unknown key belong in
 * a spec beside the code that answers them.
 *
 * The behaviour suites feed their message through the "_" fallback of a key no
 * catalog carries: what is pinned is the provider then, not the wording of a
 * translation. The last suite walks both catalogs and shows that no real
 * message relies on anything beyond that contract.
 */
import lodashGet from "lodash/get";
import { afterEach, describe, expect, it } from "vitest";

import de from "../i18n/de";
import en from "../i18n/en";
import i18nProvider, { LOCALE_STORAGE_NAME } from "./i18nProvider";

/** Neither catalog knows this key, so its answer is the caller's fallback. */
const unknownKey = "specOnlyUnknownKey";

/** Reads a message of the spec's own choosing through the real provider. */
const translate = (message: string, options?: Record<string, unknown>) =>
  i18nProvider.translate(unknownKey, { _: message, ...options });

/** Walks a catalog the way `lodashGet` reads it: dot paths down to the strings. */
const leafPaths = (value: unknown, prefix = ""): string[] =>
  value !== null && typeof value === "object"
    ? Object.entries(value as Record<string, unknown>).flatMap(([key, child]) =>
        leafPaths(child, prefix === "" ? key : `${prefix}.${key}`),
      )
    : [prefix];

afterEach(async () => {
  await i18nProvider.changeLocale("en");
});

describe("the tokens of a message", () => {
  it("substitutes every %{token} with the option of that name", () => {
    expect(translate("%{name} harvested %{total} records", { name: "CSW", total: 12 })).toBe(
      "CSW harvested 12 records",
    );
  });

  it("substitutes a repeated token and one written with blanks", () => {
    expect(translate("%{id},%{ id }", { id: 7 })).toBe("7,7");
  });

  it("leaves a token whose option is missing written out", () => {
    // The template compiler this replaces threw here with "smart_count is not
    // defined", or answered a global of the same name - `%{name}` without a
    // `name` option silently answered the window's name.
    expect(translate("%{smart_count} records loaded")).toBe("%{smart_count} records loaded");
    expect(translate("%{known} of %{unknown}", { known: 3 })).toBe("3 of %{unknown}");
    expect(i18nProvider.translate("serviceAlerts.count")).toBe("%{smart_count} alert");
  });

  it("answers an empty string for a token given as null or undefined", () => {
    expect(translate("[%{givenAsNull}]", { givenAsNull: null })).toBe("[]");
    expect(translate("[%{givenAsUndefined}]", { givenAsUndefined: undefined })).toBe("[]");
  });

  it("keeps the zero, the false and the dollar of a value", () => {
    expect(translate("%{count}=%{done}=%{shown}", { count: 0, done: false, shown: "" })).toBe(
      "0=false=",
    );
    // A value is text, not a replacement pattern of the substitution itself.
    expect(translate("%{path}", { path: "$&$1$'" })).toBe("$&$1$'");
  });

  it("hands a value over unescaped, since a React node escapes it again", () => {
    expect(translate("%{title}", { title: "A & B <b>c</b>" })).toBe("A & B <b>c</b>");
  });

  it("never evaluates the message it is given", () => {
    // The old compiler kept recognising lodash's own delimiters next to the
    // `%{token}` ones: such a message was compiled as code instead of answered.
    expect(translate("<%= 40 + 2 %> %{value}", { value: "<%= 40 + 2 %>" })).toBe(
      "<%= 40 + 2 %> <%= 40 + 2 %>",
    );
  });

  it("leaves anything which is not a token alone", () => {
    expect(translate("50 % of %{total}%", { total: 2 })).toBe("50 % of 2%");
    expect(translate("%{ unterminated")).toBe("%{ unterminated");
    expect(translate("%{}")).toBe("%{}");
  });
});

describe("the plural forms of a message", () => {
  it("chooses the form smart_count decides", () => {
    const forms = "%{smart_count} record updated |||| %{smart_count} records updated";

    expect(translate(forms, { smart_count: 1 })).toBe("1 record updated");
    expect(translate(forms, { smart_count: 0 })).toBe("0 records updated");
    expect(translate(forms, { smart_count: 2 })).toBe("2 records updated");
  });

  it("reads count and smartCount as well", () => {
    expect(translate("singular |||| plural", { count: 2 })).toBe("plural");
    expect(translate("singular |||| plural", { smartCount: 2 })).toBe("plural");
  });

  it("answers the singular form for a missing count and a count which is not a number", () => {
    expect(translate("singular |||| plural")).toBe("singular");
    expect(translate("singular |||| plural", { smart_count: "2" })).toBe("singular");
  });

  it("trims the forms and leaves a message without the separator untouched", () => {
    expect(translate("first  ||||  second", { smart_count: 2 })).toBe("second");
    expect(translate("plain %{value}", { smart_count: 2, value: 1 })).toBe("plain 1");
  });
});

describe("the answer for a key", () => {
  it("is the key itself when no catalog knows it and no fallback is given", () => {
    expect(i18nProvider.translate(unknownKey)).toBe(unknownKey);
  });

  it("is the fallback _ when no catalog knows the key", () => {
    expect(i18nProvider.translate(unknownKey, { _: "a fallback" })).toBe("a fallback");
  });

  it("is the message of the catalog when the catalog knows the key", () => {
    const key = "administration.members.title";

    expect(i18nProvider.translate(key)).toBe(lodashGet(en, key));
    expect(i18nProvider.translate(key, { _: "an ignored fallback" })).toBe(lodashGet(en, key));
  });

  it("answers a string for a key which points at a whole branch of the catalog", () => {
    const branch = "administration.members";

    expect(() => i18nProvider.translate(branch)).not.toThrow();
    expect(typeof i18nProvider.translate(branch)).toBe("string");
  });
});

describe("the locale", () => {
  const key = "administration.organization.label";

  it("answers the messages of the selected locale", async () => {
    expect(i18nProvider.getLocale()).toBe("en");
    expect(i18nProvider.translate(key)).toBe(lodashGet(en, key));

    await i18nProvider.changeLocale("de");

    expect(i18nProvider.getLocale()).toBe("de");
    expect(window.localStorage.getItem(LOCALE_STORAGE_NAME)).toBe("de");
    expect(i18nProvider.translate(key)).toBe(lodashGet(de, key));
  });
});

describe.each([
  { locale: "en", catalog: en as unknown },
  { locale: "de", catalog: de as unknown },
])("the $locale catalog", ({ locale, catalog }) => {
  it("answers no unanswered token, in either plural form", async () => {
    await i18nProvider.changeLocale(locale);

    for (const path of leafPaths(catalog)) {
      const message = lodashGet(catalog, path);
      if (typeof message !== "string" || message === "") continue;

      const options = Object.fromEntries(
        Array.from(message.matchAll(/%\{([^{}]+)\}/g), ([, name]) => [name.trim(), name.trim()]),
      );
      for (const smart_count of [1, 2]) {
        const answer = i18nProvider.translate(path, { ...options, smart_count });
        expect(answer, `${locale}.${path}`).not.toMatch(/%\{/);
      }
    }
  });

  it("carries no delimiter which asks to be compiled", () => {
    for (const path of leafPaths(catalog)) {
      const message = lodashGet(catalog, path);
      if (typeof message !== "string") continue;
      expect(message, `${locale}.${path}`).not.toMatch(/<%/);
    }
  });
});
