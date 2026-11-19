import type { HistorySource } from '../../Generic/History/historySources';

/** the lifecycle event a collecting state of the relation answers */
const harvestEvent = (collectingState: number): 'created' | 'deleted' | 'updated' => {
  if (collectingState === 1) return 'created';
  if (collectingState === 4) return 'deleted';
  return 'updated';
};

export function harvestHistorySource(serviceId: string | number): HistorySource {
  return {
    resource: 'HarvestedMetadataRelation', type: 'HarvestedMetadataRelation', label: 'serviceShow.harvestedChanges',
    filter: { 'harvesting_job__service': serviceId, 'collecting_state__in': '1,2,4' },
    toEvent: record => ({
      id: record.id, _type: 'HarvestedMetadataRelation',
      historyType: harvestEvent(record.collectingState),
      historyDate: record.historyDate,
      actionLabel: record.collectingState === 4 ? 'Removed from catalogue' : undefined,
      historyRelation: record.datasetMetadataRecord ?? record.serviceMetadataRecord,
      // Harvest results record lifecycle events, not field-level metadata diffs.
      delta: null,
    }),
  };
}
