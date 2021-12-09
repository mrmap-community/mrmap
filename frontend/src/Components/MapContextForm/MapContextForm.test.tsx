import '@testing-library/jest-dom';

import { render } from '@testing-library/react';
import React from 'react';

import { MapContextForm } from './MapContextForm';

test('Renders the MapContextForm Component', () => {
  const element = render(<MapContextForm/>);
  expect(element).toBeVisible();
});
