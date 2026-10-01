import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SimpleCard from './SimpleCard';

describe('SimpleCard', () => {
  it('preserves the standard title, subheader, divider, and padded content', () => {
    const { container } = render(<SimpleCard title="Title" subheader="Description">Content</SimpleCard>);
    expect(screen.getByText('Title')).toBeInTheDocument();
    expect(screen.getByText('Description')).toBeInTheDocument();
    expect(screen.getByRole('separator')).toBeInTheDocument();
    expect(container.querySelector('.MuiCardContent-root')).toHaveTextContent('Content');
  });

  it('supports header actions and a separately styled footer', () => {
    render(
      <SimpleCard
        headerProps={{ title: 'Runs', action: <button>Refresh</button> }}
        divider={false}
        contentProps={{ 'aria-label': 'Results' }}
        footer={<button>Show all</button>}
        footerProps={{ 'aria-label': 'Actions' }}
      >Content</SimpleCard>,
    );
    expect(screen.getByText('Runs')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument();
    expect(screen.getByLabelText('Results')).toHaveTextContent('Content');
    expect(screen.getByLabelText('Actions')).toContainElement(screen.getByRole('button', { name: 'Show all' }));
    expect(screen.queryByRole('separator')).not.toBeInTheDocument();
  });

  it('omits unused sections and allows children to own their layout', () => {
    const { container } = render(<SimpleCard contentProps={false}><section>Timeline</section></SimpleCard>);
    expect(screen.getByText('Timeline')).toBeInTheDocument();
    expect(container.querySelector('.MuiCardHeader-root')).toBeNull();
    expect(container.querySelector('.MuiCardContent-root')).toBeNull();
    expect(container.querySelector('.MuiCardActions-root')).toBeNull();
    expect(screen.queryByRole('separator')).not.toBeInTheDocument();
  });
});
