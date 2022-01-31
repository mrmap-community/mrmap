import '@testing-library/jest-dom';
import { shallow } from 'enzyme';
import React from 'react';
import { TreeFormField } from './TreeFormField';


describe('TreeFormField component', () => {
  const requiredProps = {};

  const getComponent = (props?:any) => shallow((
    <TreeFormField
      {...requiredProps}
      {...props}
    />
  ));

  it('renders the component', () => {
    const component = getComponent();
    expect(component).toBeDefined();
  });
});
