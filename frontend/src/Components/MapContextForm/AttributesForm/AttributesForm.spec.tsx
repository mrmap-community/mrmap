import React from 'react';

import { render, waitFor } from '@testing-library/react';

import { AttributesForm } from './AttributesForm';


describe('AttributesForm component', () => {
  const requiredProps = {};

  const renderComponent = (props?:any) => render((
    <AttributesForm
      {...requiredProps}
      {...props}
    />
  ));

  it.skip('renders the component', async() => {
    const component = renderComponent();
    await waitFor(() => {
      expect(component).toBeDefined();
    });
  });
});
