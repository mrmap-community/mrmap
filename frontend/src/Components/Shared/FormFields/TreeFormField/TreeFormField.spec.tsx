import '@testing-library/jest-dom';
import { render } from '@testing-library/react';
import React from 'react';
import { TreeFormField } from './TreeFormField';



describe('TreeFormField component', () => {
  const requiredProps = {};

  const getComponent = (props?:any) => render((
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
