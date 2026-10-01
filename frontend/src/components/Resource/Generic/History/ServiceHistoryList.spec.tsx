import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useGetList } from 'react-admin';
import ServiceHistoryCard from '../ServiceShow/ServiceHistoryCard';
const state = vi.hoisted(() => ({ resource: 'CatalogueService', id: 'service-1' }));
vi.mock('react-admin', () => ({ Loading: () => <div>Loading history</div>, useGetList: vi.fn(), useRecordContext: (record?: unknown) => record ?? { id: state.id }, useResourceContext: () => state.resource, useTranslate: () => (key: string) => key }));
vi.mock('../../../../jsonapi/hooks/useOperation', () => ({ default: () => ({}) }));
const serviceData = [{ id: 'same-id', historyType: 'updated', historyDate: '2026-10-01T10:00:00Z', historyRelation: { id: 'service-1' }, delta: [{ field: 'title', old: 'Old', new: 'New title' }] }];
const childData = [{ ...serviceData[0], historyDate: '2026-10-01T11:00:00Z' }];
const harvestData = [1, 2, 4].map(collectingState => ({ id: collectingState, collectingState, historyDate: `2026-10-01T12:0${collectingState}:00Z`, datasetMetadataRecord: { id: `record-${collectingState}` } }));
beforeEach(() => {
 state.id = 'service-1'; vi.mocked(useGetList).mockReset();
 vi.mocked(useGetList, { partial: true }).mockImplementation(resource => ({ data: resource === 'HarvestedMetadataRelation' ? harvestData : resource === 'HistoricalFeatureType' || resource === 'HistoricalLayer' ? childData : serviceData, isPending: false }));
});
describe('service event sources', () => {
 it.each([['WebMapService', 'HistoricalLayer', 'Layer'], ['WebFeatureService', 'HistoricalFeatureType', 'FeatureType']])('combines %s and its child history', (resource, endpoint, type) => {
  state.resource = resource; render(<ServiceHistoryCard />);
  expect(useGetList).toHaveBeenCalledWith(endpoint, expect.objectContaining({ meta: { jsonApiParams: expect.objectContaining({ 'filter[service]': 'service-1' }) } }));
  const events = screen.getAllByRole('button', { name: new RegExp(`^(${resource}|${type}) `) });
  expect(events).toHaveLength(2); expect(events[0]).toHaveAccessibleName(new RegExp(`^${type} `));
  fireEvent.click(events[0]); expect(screen.getByText('New title')).toBeInTheDocument();
 });
 it('combines CSW changes with new, updated, and removed harvest records', () => {
  state.resource = 'CatalogueService'; render(<ServiceHistoryCard />);
  expect(useGetList).toHaveBeenCalledWith('HarvestedMetadataRelation', expect.objectContaining({ filter: { harvesting_job__service: 'service-1', collecting_state__in: '1,2,4' }, sort: { field: 'historyDate', order: 'DESC' } }));
  expect(screen.getByRole('button', { name: /HarvestedMetadataRelation record-1, Created/ })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /HarvestedMetadataRelation record-2, Updated/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /HarvestedMetadataRelation record-4, Removed from catalogue/ }));
  expect(screen.getByRole('region', { name: 'Selected event details' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^CatalogueService / })).toBeInTheDocument();
 });
 it('resets selection when switching service type', () => {
  state.resource = 'CatalogueService'; const { rerender } = render(<ServiceHistoryCard />);
  fireEvent.click(screen.getByRole('button', { name: /^CatalogueService / }));
  state.resource = 'WebFeatureService'; rerender(<ServiceHistoryCard />);
  expect(screen.queryByRole('region', { name: 'Selected event details' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /^HarvestedMetadataRelation / })).not.toBeInTheDocument();
 });
});
