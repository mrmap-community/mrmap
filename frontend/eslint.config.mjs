import globals from "globals";
import pluginJs from "@eslint/js";
import tseslint from "typescript-eslint";
import pluginReactConfig from "eslint-plugin-react/configs/recommended.js";
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
  { files: ["**/*.ts", "**/*.tsx"], rules: { "react/prop-types": "off" } },
];