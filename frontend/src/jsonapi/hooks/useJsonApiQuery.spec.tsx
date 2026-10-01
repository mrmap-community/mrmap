import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import useJsonApiQuery from './useJsonApiQuery';

const state = vi.hoisted(() => ({
  name: 'Service',
  fieldsets: [] as { type: string; fields: string[] }[],
  omit: [] as string[],
  selected: [] as string[],
  columns: [
    { source: 'title', index: '0' },
    { source: 'createdBy', index: '1' },
    { source: 'actions', index: '2' },
  ],
}));
vi.mock('react-admin', () => ({
  useResourceDefinition: () => ({ name: state.name, options: { list: { sparseFieldsets: state.fieldsets } } }),
  useStore: (key: string) => [key.endsWith('availableColumns') ? state.columns : key.endsWith('.omit') ? state.omit : state.selected],
}));
vi.mock('./useSparseFieldsForOperation', () => ({
  default: () => ({ operation: {}, sparseFields: { Service: ['title', 'created_by'], Other: ['name'] } }),
}));
vi.mock('../utils', () => ({ getIncludeOptions: () => ['createdBy'] }));

beforeEach(() => {
  state.name = 'Service';
  state.fieldsets = [];
  state.omit = [];
  state.selected = [];
});
describe('useJsonApiQuery', () => {
  it('derives supported sparse fields without explicit fieldsets and retains include casing', () => {
    const { result } = renderHook(() => useJsonApiQuery({}));
    expect(result.current).toEqual({ 'fields[Service]': 'title,created_by', include: 'createdBy' });
  });
  it('updates omitted columns and never includes custom action columns', () => {
    const { result, rerender } = renderHook(() => useJsonApiQuery({}));
    state.omit = ['createdBy'];
    rerender();
    expect(result.current).toEqual({ 'fields[Service]': 'title', include: '' });
    state.selected = ['1', '2'];
    rerender();
    expect(result.current).toEqual({ 'fields[Service]': 'created_by', include: 'createdBy' });
  });
  it('merges mandatory fields and preserves related fieldsets', () => {
    state.fieldsets = [{ type: 'Service', fields: ['title', 'isSecured'] }, { type: 'User', fields: ['username'] }];
    const { result } = renderHook(() => useJsonApiQuery({}));
    expect(result.current['fields[Service]']).toBe('title,is_secured,created_by');
    expect(result.current['fields[User]']).toBe('username');
  });
  it('adds primary fields when only a related fieldset is configured', () => {
    state.fieldsets = [{ type: 'User', fields: ['username'] }];
    const { result } = renderHook(() => useJsonApiQuery({}));
    expect(result.current['fields[Service]']).toBe('title,created_by');
  });
  it('does not emit an empty primary fieldset for unsupported columns', () => {
    state.name = 'Other';
    const { result } = renderHook(() => useJsonApiQuery({}));
    expect(result.current).toEqual({ include: '' });
  });
});
