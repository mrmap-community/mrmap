// do some test init

const localStorageMock = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
};

global.localStorage = localStorageMock;

// react-testing-library displays your component as document.body,
// This will add a custom assertion to jest-dom
import '@testing-library/jest-dom';

// get rid of the necessity to import React
window.React = require('react');

// Error: Uncaught [TypeError: window.matchMedia is not a function]
// https://jestjs.io/docs/26.x/manual-mocks
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(), // deprecated
    removeListener: jest.fn(), // deprecated
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});

// https://github.com/umijs/umi/issues/5138
function mockUmi() {
  const original = jest.requireActual('umi');
  return {
    ...original,
    useIntl: () => {
      return {
        formatMessage: ({ id, defaultMessage }) => {
          return defaultMessage;
        },
      };
    },
    FormattedMessage: ({ id, defaultMessage }) => {
      return <>{defaultMessage}</>;
    },
  };
}
jest.mock('umi', () => mockUmi());
