import { useGetList, useRecordContext, useResourceContext } from "react-admin"



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
    <>huhu</>
  )
}


export default OverviewtTab