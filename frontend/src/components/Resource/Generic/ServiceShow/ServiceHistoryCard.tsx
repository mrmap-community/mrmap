import { useMemo } from 'react';
import { useRecordContext, useResourceContext } from 'react-admin';

import useOperation from '../../../../jsonapi/hooks/useOperation';
import { harvestHistorySource } from '../../CatalogueService/Show/harvestHistorySource';
import HistoryList from '../History/HistoryList';
import { historicalSource } from '../History/historySources';

const ServiceHistoryCard = () => {
  const resource = useResourceContext();
  const record = useRecordContext();
  const operation = useOperation(`list_Historical${resource}`);
  const sources = useMemo(() => {
    if (!record || !resource) return [];
    const service = historicalSource(`Historical${resource}`, resource, 'Service changes', record.id, 'historyRelation');
    switch (resource) {
      case 'WebMapService': return [service, historicalSource('HistoricalLayer', 'Layer', 'Layer changes', record.id, 'service')];
      case 'WebFeatureService': return [service, historicalSource('HistoricalFeatureType', 'FeatureType', 'serviceShow.featureTypeChanges', record.id, 'service')];
      case 'CatalogueService': return [service, harvestHistorySource(record.id)];
      default: return [];
    }
  }, [resource, record?.id]);
  if (!operation || !record || !sources.length) return null;
  return <HistoryList variant="timeline" key={`${resource}:${record.id}`} sources={sources} record={record} />;
}


export default ServiceHistoryCard;