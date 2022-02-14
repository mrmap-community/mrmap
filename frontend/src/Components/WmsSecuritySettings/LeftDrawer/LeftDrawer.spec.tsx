import '@testing-library/jest-dom/extend-expect';
import { render } from '@testing-library/react';
import React from 'react';
import { LeftDrawer } from './LeftDrawer';

describe('LeftDrawer', () => {
  it('is defined', () => {
    expect(LeftDrawer).toBeDefined();
  });

  it('can be rendered', () => {
    const { container } = render(<LeftDrawer/>);
    expect(container).toBeVisible();
  });
});
