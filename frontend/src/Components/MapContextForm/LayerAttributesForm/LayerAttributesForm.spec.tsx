import '@testing-library/jest-dom';
import React from 'react';

import { shallow } from 'enzyme';

import { LayerAttributesForm } from './LayerAttributesForm';


describe('LayerAttributesForm component', () => {
  const requiredProps = {};

  const getComponent = (props?:any) => shallow((
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
