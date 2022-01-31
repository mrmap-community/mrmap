import { render } from '@testing-library/react';
import React from 'react';
import { MapContextForm } from './MapContextForm';


describe('MapContextForm component', () => {
  const requiredProps = {};

  const getComponent = (props?:any) => render((
    <MapContextForm
      {...requiredProps}
      {...props}
    />
  ));

  it('renders the component', () => {
    const component = getComponent();
    expect(component).toBeDefined();
  });
});
