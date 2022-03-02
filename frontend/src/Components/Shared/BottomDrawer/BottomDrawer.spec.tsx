import '@testing-library/jest-dom/extend-expect';
import { render } from '@testing-library/react';
import React from 'react';
import { BottomDrawer } from './BottomDrawer';

describe('BottomDrawer', () => {
  it('is defined', () => {
    expect(BottomDrawer).toBeDefined();
  });

  it('can be rendered', () => {
    const { container } = render(<BottomDrawer/>);
    expect(container).toBeVisible();
  });
});
