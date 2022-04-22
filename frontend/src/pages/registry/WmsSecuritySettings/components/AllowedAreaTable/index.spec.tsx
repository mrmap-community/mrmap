import '@testing-library/jest-dom/extend-expect';
import { render } from '@testing-library/react';
import AllowedAreaTable from '.';

describe('AreaDigitizeToolbar', () => {
  it('is defined', () => {
    expect(AllowedAreaTable).toBeDefined();
  });

  it('can be rendered', () => {
    const { container } = render(<AllowedAreaTable />);
    expect(container).toBeVisible();
  });
});
