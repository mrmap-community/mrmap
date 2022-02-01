import '@testing-library/jest-dom';
import { shallow } from 'enzyme';
import React from 'react';
import { TreeManager } from './TreeManager';


describe('TreeFormField component', () => {
  const requiredProps = {};

  const getComponent = (props?:any) => shallow((
    <TreeManager
      {...requiredProps}
      {...props}
    />
  ));

  it('renders the component', () => {
    const component = getComponent();
    expect(component).toBeDefined();
  });
});
