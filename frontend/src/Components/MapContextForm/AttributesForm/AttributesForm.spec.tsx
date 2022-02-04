import { render, waitFor } from '@testing-library/react';
import React from 'react';
import { AttributesForm } from './AttributesForm';


describe('AttributesForm component', () => {
  const requiredProps = {};

  const getComponent = (props?:any) => render((
    <AttributesForm
      {...requiredProps}
      {...props}
    />
  ));

  it.skip('renders the component', async() => {
    const component = getComponent();
    await waitFor(() => {
      expect(component).toBeDefined();
    });
  });
});
