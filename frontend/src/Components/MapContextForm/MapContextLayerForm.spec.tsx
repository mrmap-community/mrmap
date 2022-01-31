import '@testing-library/jest-dom';
import { render } from '@testing-library/react';
import React from 'react';
import { MapContextLayerForm } from './MapContextLayerForm';


describe('MapContextLayerForm component', () => {
  const requiredProps = {};

  const getComponent = (props?:any) => render((
    <MapContextLayerForm
      {...requiredProps}
      {...props}
    />
  ));

  it('renders the component', () => {
    const component = getComponent();
    expect(component).toBeDefined();
  });
});
