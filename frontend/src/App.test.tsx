import { render } from '@testing-library/react';
import React from 'react';

import App from './App';

test('Renders the App Component', () => {
  const element = render(<App/>);
  expect(element).toMatchSnapshot();
});
