import { olMap } from '@/utils/map';
import '@testing-library/jest-dom/extend-expect';
import { render } from '@testing-library/react';
import { AreaDigitizeToolbar } from '.';

describe('AreaDigitizeToolbar', () => {
  it('is defined', () => {
    expect(AreaDigitizeToolbar).toBeDefined();
  });

  it('can be rendered', () => {
    const { container } = render(<AreaDigitizeToolbar map={olMap} />);
    expect(container).toBeVisible();
  });
});
