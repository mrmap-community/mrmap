import '@testing-library/jest-dom/extend-expect';
import { render } from '@testing-library/react';
import React from 'react';
import { RightDrawer } from './RightDrawer';

jest.mock('../../../Repos/DatasetMetadataRepo');

describe('RightDrawer', () => {
  it('is defined', () => {
    expect(RightDrawer).toBeDefined();
  });

  it('can be rendered', () => {
    const { container } = render(<RightDrawer />);
    expect(container).toBeVisible();
  });
});
