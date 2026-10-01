import type { HistorySource } from '../../Generic/History/historySources';

export function harvestHistorySource(serviceId: string | number): HistorySource {
  return {
    resource: 'HarvestedMetadataRelation', type: 'HarvestedMetadataRelation', label: 'serviceShow.harvestedChanges',
    filter: { 'harvesting_job__service': serviceId, 'collecting_state__in': '1,2,4' },
    toEvent: record => ({
      id: record.id, _type: 'HarvestedMetadataRelation',
      historyType: record.collectingState === 1 ? 'created' : record.collectingState === 4 ? 'deleted' : 'updated',
      historyDate: record.historyDate,
      actionLabel: record.collectingState === 4 ? 'Removed from catalogue' : undefined,
      historyRelation: record.datasetMetadataRecord ?? record.serviceMetadataRecord,
      // Harvest results record lifecycle events, not field-level metadata diffs.
      delta: null,
    }),
  };
}
