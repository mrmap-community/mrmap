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
