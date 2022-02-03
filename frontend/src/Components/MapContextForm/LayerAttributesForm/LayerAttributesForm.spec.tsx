import '@testing-library/jest-dom';
import { render } from '@testing-library/react';
import React from 'react';
import { LayerAttributesForm } from './LayerAttributesForm';


describe('LayerAttributesForm component', () => {
  const requiredProps = {};

  const getComponent = (props?:any) => render((
    <LayerAttributesForm
      {...requiredProps}
      {...props}
    />
  ));

  it('renders the component', () => {
    const component = getComponent();
    expect(component).toBeDefined();
  });
});
