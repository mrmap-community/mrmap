import { useMemo, type ComponentType } from 'react';
import { ResourceContext, useRecordContext, useResourceContext } from 'react-admin';

import { RelatedResource } from '../../../providers/dataProvider';


export interface ServiceMonitoringTabProps {
  /** resource of the monitoring setting of the shown service */
  settingResource: string;
  /** component which lists the settings of the shown service */
  ListComponent: ComponentType<{ relatedResource?: Partial<RelatedResource> }>;
}

/** Tab which lists the monitoring settings of the shown service. */
export const ServiceMonitoringTab = ({
  settingResource,
  ListComponent
}: ServiceMonitoringTabProps) => {
  const resource = useResourceContext()
  const record = useRecordContext()

  const relatedResource = useMemo<RelatedResource | undefined>(() => {
    if (resource !== undefined && record !== undefined) {
      return { resource, id: record.id }
    }
  }, [resource, record])

  return (
    <ResourceContext value={settingResource}>
      <ListComponent relatedResource={relatedResource} />
    </ResourceContext>
  )
}

export default ServiceMonitoringTab
