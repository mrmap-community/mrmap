import '@testing-library/jest-dom';

import { render } from '@testing-library/react';
import React from 'react';

import { MapContext } from './MapContext';

test('Renders the MapContext Component', () => {
  const element = render(<MapContext/>);
  expect(element).toMatchSnapshot();
});
