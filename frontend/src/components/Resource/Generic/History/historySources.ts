import type { RaRecord } from 'react-admin';
import type { TimelineRecord } from './HistoryTimeline';

/** Describes an event feed, independently of the service that displays it. */
export interface HistorySource {
  resource: string;
  type: string;
  label: string;
  filter: Record<string, string | number | boolean>;
  jsonApiParams?: Record<string, string | number>;
  toEvent: (record: RaRecord) => TimelineRecord;
}

export function historicalSource(resource: string, type: string, label: string, parentId: string | number, relation: 'historyRelation' | 'service'): HistorySource {
  return {
    resource, type, label,
    filter: relation === 'historyRelation' ? { changed_or_created: true } : { changed_or_deleted: true },
    jsonApiParams: { include: 'historyUser', 'fields[User]': 'username,string_representation', [`filter[${relation}]`]: parentId },
    toEvent: record => ({ ...record, id: record.id, historyType: record.historyType, historyDate: record.historyDate, _type: type }),
  };
}
