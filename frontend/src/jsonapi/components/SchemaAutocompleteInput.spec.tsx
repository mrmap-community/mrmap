import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { RaRecord } from 'react-admin';
import SchemaAutocompleteInput from './SchemaAutocompleteInput';

const state = vi.hoisted(() => ({
  value: undefined as RaRecord | RaRecord[] | undefined,
  search: [] as RaRecord[],
  fetched: undefined as RaRecord[] | undefined,
}));
vi.mock('react-hook-form', () => ({ useWatch: () => state.value }));
vi.mock('../hooks/useSchemaRecordRepresentation', () => ({ default: () => (record: RaRecord) => record.stringRepresentation }));
vi.mock('react-admin', () => {
  const Input = ({ choices }: { choices: RaRecord[] }) => <select aria-label="Operations">{choices.map(choice => <option key={choice.id} value={choice.id}>{choice.stringRepresentation}</option>)}</select>;
  return {
    AutocompleteArrayInput: Input,
    AutocompleteInput: Input,
    useRecordContext: () => undefined,
    useGetList: () => ({ data: state.search }),
    useGetMany: () => ({ data: state.fetched }),
  };
});
beforeEach(() => {
  state.value = undefined;
  state.fetched = undefined;
  state.search = [{ id: 20, stringRepresentation: 'GetMap' }, { id: 21, stringRepresentation: 'GetFeatureInfo' }];
});
describe('SchemaAutocompleteInput choices', () => {
  it.each([true, false])('shows search results once with multiple=%s', multiple => {
    render(<SchemaAutocompleteInput reference="WebMapServiceOperation" source="operations" multiple={multiple ? true : undefined} />);
    expect(screen.getAllByRole('option')).toHaveLength(2);
    expect(screen.getAllByRole('option', { name: 'GetMap' })).toHaveLength(1);
  });
  it('deduplicates selected and searched records by ID and keeps selected records outside the search', () => {
    state.value = [{ id: 20, stringRepresentation: 'GetMap' }, { id: 22, stringRepresentation: 'Other' }];
    state.fetched = state.value;
    state.search[0] = { id: '20', stringRepresentation: 'GetMap' };
    render(<SchemaAutocompleteInput reference="WebMapServiceOperation" source="operations" multiple />);
    expect(screen.getAllByRole('option')).toHaveLength(3);
    expect(screen.getAllByRole('option', { name: 'GetMap' })).toHaveLength(1);
    expect(screen.getByRole('option', { name: 'Other' })).toBeInTheDocument();
  });
  it('retains an included selection without a getMany response and allows distinct IDs with the same label', () => {
    state.value = { id: 99, stringRepresentation: 'GetMap' };
    const { rerender } = render(<SchemaAutocompleteInput reference="WebMapServiceOperation" source="operation" />);
    expect(screen.getAllByRole('option', { name: 'GetMap' })).toHaveLength(2);
    state.search = [];
    rerender(<SchemaAutocompleteInput reference="WebMapServiceOperation" source="operation" />);
    expect(screen.getAllByRole('option')).toHaveLength(1);
    expect(screen.getByRole('option')).toHaveValue('99');
  });
});
