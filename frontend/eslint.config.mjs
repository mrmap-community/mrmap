import globals from "globals";
import pluginJs from "@eslint/js";
import tseslint from "typescript-eslint";
import pluginReactConfig from "eslint-plugin-react/configs/recommended.js";
import reactHooks from "eslint-plugin-react-hooks";
import { fixupConfigRules } from "@eslint/compat";
import perfectionist from 'eslint-plugin-perfectionist'

export default [
  { ignores: ["coverage/**", "dist/**", "node_modules/**"] },
  {
    languageOptions: { globals: { ...globals.browser, ...globals.vitest } },
  },
  { files: ["**/*.js", "**/*.jsx"], languageOptions: { globals: globals.node } },
  pluginJs.configs.recommended,
  ...tseslint.configs.recommended,
  // eslint-plugin-react still declares ESLint <=9; package.json overrides its peer.
  // Keep this adapter for the rule APIs removed in v10 until the plugin supports it.
  ...fixupConfigRules(pluginReactConfig),
  {
    "plugins": {
      perfectionist
    },
    "settings": {
      "react": {
        "version": "detect"
      }
    },
    "rules": {
      "react/react-in-jsx-scope": "off",
      "react/jsx-uses-react": "off",
      "@typescript-eslint/no-unused-expressions": ["error", { allowShortCircuit: true, allowTernary: true }],
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" }],
      'perfectionist/sort-imports': [
        'error',
        {
          type: 'natural',
          order: 'asc',
          groups: [
            'type',
            'react',
            'nanostores',
            ['builtin', 'external'],
            'type-internal',
            'internal',
            ['type-parent', 'type-sibling', 'type-index'],
            ['parent', 'sibling', 'index'],
            'side-effect',
            'style',
            'unknown',
          ],
          customGroups: [
            { groupName: 'react', elementNamePattern: ['^react$', '^react-'] },
            { groupName: 'nanostores', elementNamePattern: '^@nanostores/' },
          ],
          newlinesBetween: 1,
          internalPattern: [
            '^@/components/',
            '^@/stores/',
            '^@/pages/',
            '^@/lib/',
          ],
        },
      ],
    }
  },
  {
    files: ["**/*.ts", "**/*.tsx"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      // The audit (#1466) found five render-storm bugs that are exactly this
      // rule's class; CI could not see them while the plugin was absent.
      "react-hooks/exhaustive-deps": "error",
    },
  },
  { files: ["**/*.ts", "**/*.tsx"], rules: { "react/prop-types": "off" } },
];
