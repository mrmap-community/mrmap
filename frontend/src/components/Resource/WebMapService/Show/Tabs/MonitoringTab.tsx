import { useMemo } from 'react';
import { ResourceContext, useRecordContext, useResourceContext } from 'react-admin';
import { Fragment } from 'react/jsx-runtime';
import ListWithDialogs from '../../../../../jsonapi/components/ListWithDialogs';
import { RelatedResource } from '../../../../../providers/dataProvider';
import ListWebMapServiceMonitoringSetting from '../../../Monitoring/WebMapServiceMonitoringSetting/ListWebMapServiceMonitoringSetting';


export const MonitoringTab = () => {
  const resource = useResourceContext()
  const record = useRecordContext()

  const relatedResource = useMemo<RelatedResource | undefined>(()=>{
    if (resource !== undefined && record !== undefined){
      return {resource, id: record.id}
    }
  },[resource, record])

  return (
    <Fragment>
      <ResourceContext
        value='WebMapServiceMonitoringSetting'
      >
        <ListWebMapServiceMonitoringSetting
          relatedResource={relatedResource}
        />
      </ResourceContext>

      <ResourceContext
        value='WebMapServiceMonitoringRun'
      >
        <ListWithDialogs
          listGuesserProps={
            {
              relatedResource: relatedResource
            }
          }
        />
      </ResourceContext>
    </Fragment>
  )
}

export default MonitoringTab