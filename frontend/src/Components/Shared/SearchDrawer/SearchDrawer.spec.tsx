import '@testing-library/jest-dom/extend-expect';
import { render } from '@testing-library/react';
import React from 'react';
import { SearchDrawer } from './SearchDrawer';
jest.mock('../../Repos/DatasetMetadataRepo');

describe('SearchDrawer', () => {
  it('is defined', () => {
    expect(SearchDrawer).toBeDefined();
  });

  it('can be rendered', () => {
    const { container } = render(<SearchDrawer />);
    expect(container).toBeVisible();
  });
});
