import { mount } from 'enzyme';
import React from 'react';

import { MapContext } from './MapContext';

describe('MapContext component', () => {
  const requiredProps = {};

  const getComponent = (props?:any) => mount((
    <MapContext
      {...requiredProps}
      {...props}
    />
  ));

  it('renders the component', () => {
    const component = getComponent();
    expect(component).toBeDefined();
  });
});
