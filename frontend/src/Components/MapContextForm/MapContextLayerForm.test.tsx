import '@testing-library/jest-dom';

import { render } from '@testing-library/react';
import React from 'react';

import { MapContextLayerForm } from './MapContextLayerForm';

test('Renders the MapContextLayerForm Component', () => {
  const element = render(<MapContextLayerForm/>);
  expect(element).toMatchSnapshot();
});
