/* eslint-disable @typescript-eslint/no-empty-function */
import '@testing-library/jest-dom/extend-expect';
import { render } from '@testing-library/react';
import React from 'react';
import { olMap } from '../../../Utils/MapUtils';
import { AreaDigitizeToolbar } from './AreaDigitizeToolbar';

describe('AreaDigitizeToolbar', () => {

  it('is defined', () => {
    expect(AreaDigitizeToolbar).toBeDefined();
  });

  it('can be rendered', () => {
    const { container } = render(
      <AreaDigitizeToolbar map={olMap} />
    );
    expect(container).toBeVisible();
  });

});
