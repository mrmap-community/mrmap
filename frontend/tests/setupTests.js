// do some test init

// react-testing-library displays your component as document.body,
// This will add a custom assertion to jest-dom
import '@testing-library/jest-dom';

const localStorageMock = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
};

global.localStorage = localStorageMock;
