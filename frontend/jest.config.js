module.exports = {
  testURL: 'http://localhost:8000',
  verbose: false,
  setupFilesAfterEnv: ['./tests/setupTests.jsx'],
  globals: {
    ANT_DESIGN_PRO_ONLY_DO_NOT_USE_IN_YOUR_PRODUCTION: false,
    localStorage: null,
  },
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  modulePathIgnorePatterns: ['<rootDir>/src/e2e'],
};
