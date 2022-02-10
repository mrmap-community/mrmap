import '@testing-library/jest-dom';
import { render, waitFor } from '@testing-library/react';
import React from 'react';
import { LayerAttributesForm } from './LayerAttributesForm';


describe('LayerAttributesForm component', () => {
  const requiredProps = {};

  const renderComponent = (props?:any) => render((
    <LayerAttributesForm
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
