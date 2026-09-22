import { SimpleShowLayout, useGetList, useRecordContext, useResourceContext } from "react-admin";

import { RaRecord, UrlField, WithRecord } from 'react-admin';
import { prepareGetCapabilititesUrl } from "../../../../../ows-lib/OwsContext/utils";

const UpdateJobStats = () => {
  const record = useRecordContext()

  const {data} = useGetList(
    "LayerHistory",
    {
      filter: {
        "history_change_reason__icontains": record?.id
      },
      meta: {
        // TODO: sparsefields
        
      }
    }
  )
}


const OverviewtTab = () => {


  // Monitoring statistics
  // Update statistics
  // General State => isSearchable, isActive, isSecured, isSpatialSecured

  const record = useRecordContext()
  const resource = useResourceContext()

  const { data: monitoringRuns } = useGetList(
    "WebMapServiceMonitoringRun", 
    {
      meta: {
        relatedResource: {
          resource: resource,
          id: record?.id
        }
      }
    }
  )




  const { data: updateJobs } = useGetList(
    "WebMapServiceUpdateJob", 
    {
      sort: {field: 'doneAt', order: 'DESC'},
      meta: {
        relatedResource: {
          resource: resource,
          id: record?.id
        }
      }
    }
  )





  console.log(
    record,
    monitoringRuns,
    updateJobs
  )

  return (
    <SimpleShowLayout>
      <UrlField source="xmlBackupFile" label='show stored capabilitites'/>
      <WithRecord 
          label="show remote capabilities" 
          render={(record: RaRecord) => {
              const url = record.operationUrls?.find((operationUrl: RaRecord)=> (operationUrl.operation === 1 && operationUrl.method === 1));
              url.url = prepareGetCapabilititesUrl(
                      url.url,
                      "WMS",
                      record.version.toString().split('').join('.')
                  ).href
              return url ? <UrlField record={url} source="url"/> : null; 
          }}
      />
      <UrlField source="xmlBackupFileSecured" label='show secured capabilitites'/>
    </SimpleShowLayout>
  )
}


export default OverviewtTab