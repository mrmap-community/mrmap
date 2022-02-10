import '@testing-library/jest-dom/extend-expect';
import { render } from '@testing-library/react';
import React from 'react';
import { AllowedAreaList } from './AllowedAreaList';


describe('AllowedAreaList', () => {
  it('is defined', () => {
    expect(AllowedAreaList).toBeDefined();
  });

  it('can be rendered', () => {
    const { container } = render(<AllowedAreaList />);
    expect(container).toBeVisible();
  });
});
