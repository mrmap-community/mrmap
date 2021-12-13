import '@testing-library/jest-dom';

import { shallow } from 'enzyme';
import React from 'react';

import { MapContextLayerForm } from './MapContextLayerForm';

describe('MapContextLayerForm component', () => {
  const requiredProps = {};

  const getComponent = (props?:any) => shallow((
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
