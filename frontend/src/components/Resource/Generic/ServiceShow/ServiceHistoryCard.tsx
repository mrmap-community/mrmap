import { useMemo } from 'react';
import { useRecordContext, useResourceContext } from 'react-admin';

import useOperation from '../../../../jsonapi/hooks/useOperation';
import { harvestHistorySource } from '../../CatalogueService/Show/harvestHistorySource';
import HistoryList from '../History/HistoryList';
import { historicalSource } from '../History/historySources';

const ServiceHistoryCard = () => {
  const resource = useResourceContext();
  const record = useRecordContext();
  const recordId = record?.id;
  const operation = useOperation(`list_Historical${resource}`);
  const sources = useMemo(() => {
    if (recordId === undefined || !resource) return [];
    const service = historicalSource(`Historical${resource}`, resource, 'Service changes', recordId, 'historyRelation');
    switch (resource) {
      case 'WebMapService': return [service, historicalSource('HistoricalLayer', 'Layer', 'Layer changes', recordId, 'service')];
      case 'WebFeatureService': return [service, historicalSource('HistoricalFeatureType', 'FeatureType', 'serviceShow.featureTypeChanges', recordId, 'service')];
      case 'CatalogueService': return [service, harvestHistorySource(recordId)];
      default: return [];
    }
  }, [resource, recordId]);
  if (!operation || !record || !sources.length) return null;
  return <HistoryList variant="timeline" key={`${resource}:${record.id}`} sources={sources} record={record} />;
}


export default ServiceHistoryCard;