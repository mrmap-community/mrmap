import '@testing-library/jest-dom';
import { shallow } from 'enzyme';
import React from 'react';
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
