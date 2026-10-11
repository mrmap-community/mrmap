import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SchemaFormFields from './SchemaFormFields';

vi.mock('../hooks/useFieldsForOperation', () => ({
  useFieldsForOperation: () => [
    { component: ({ label }: { label: string }) => <span>{label}</span>, props: { source: 'title', label: 'Title' } },
    { component: () => <span>Read only</span>, props: { source: 'id', disabled: true } },
  ],
}));
describe('SchemaFormFields', () => {
  it('applies updated overrides and keeps schema-disabled fields hidden', () => {
    const component = ({ label, record }: { label: string; record?: { id: number } }) => <span>{label} {record?.id}</span>;
    const { rerender } = render(<SchemaFormFields operationId="partial_update_Service" overrides={[{ component, props: { source: 'title', label: 'First' } }]} record={{ id: 1 }} />);
    expect(screen.getByText('First 1')).toBeInTheDocument();
    expect(screen.queryByText('Read only')).not.toBeInTheDocument();
    rerender(<SchemaFormFields operationId="partial_update_Service" overrides={[{ component, props: { source: 'title', label: 'Second' } }]} record={{ id: 2 }} />);
    expect(screen.getByText('Second 2')).toBeInTheDocument();
    expect(screen.queryByText('First 1')).not.toBeInTheDocument();
  });
});
