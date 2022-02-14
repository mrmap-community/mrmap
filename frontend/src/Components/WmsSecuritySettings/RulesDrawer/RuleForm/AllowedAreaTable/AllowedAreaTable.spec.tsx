import '@testing-library/jest-dom/extend-expect';
import { render } from '@testing-library/react';
import React from 'react';
import { AllowedAreaTable } from './AllowedAreaTable';


describe('AllowedAreaTable', () => {
  it('is defined', () => {
    expect(AllowedAreaTable).toBeDefined();
  });

  it('can be rendered', () => {
    const { container } = render(<AllowedAreaTable />);
    expect(container).toBeVisible();
  });
});
