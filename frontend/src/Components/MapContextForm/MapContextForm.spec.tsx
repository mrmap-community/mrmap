import '@testing-library/jest-dom';
import { shallow } from 'enzyme';
import React from 'react';
import { MapContextForm } from './MapContextForm';


describe('MapContextForm component', () => {
  const requiredProps = {};

  const getComponent = (props?:any) => shallow((
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
