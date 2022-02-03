import { render } from '@testing-library/react';
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

  it('renders the component', () => {
    const component = getComponent();
    expect(component).toBeDefined();
  });
});
