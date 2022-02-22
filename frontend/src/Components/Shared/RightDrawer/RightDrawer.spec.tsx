import '@testing-library/jest-dom/extend-expect';
import { render, waitFor } from '@testing-library/react';
import React from 'react';
import { RightDrawer } from './RightDrawer';


describe('RightDrawer', () => {
  it('is defined', () => {
    expect(RightDrawer).toBeDefined();
  });

  it('can be rendered', async() => {
    const { container } = render(<RightDrawer />);
    await waitFor(() => {
      expect(container).toBeVisible();
    });
  });
});
