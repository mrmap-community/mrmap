import '@testing-library/jest-dom';
import { shallow } from 'enzyme';
import React from 'react';
import { AttributesForm } from './AttributesForm';


describe('AttributesForm component', () => {
  const requiredProps = {};

  const getComponent = (props?:any) => shallow((
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
