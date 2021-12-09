import '@testing-library/jest-dom';

import { render } from '@testing-library/react';
import React from 'react';

import { TreeFormField } from './TreeFormField';

test('Renders the TreeFormField Component', () => {
  const element = render(<TreeFormField treeData={[]}/>);
  expect(element).toMatchSnapshot();
});
