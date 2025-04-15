import { snakeCase } from 'lodash';
import { useMemo } from 'react';
import { RaRecord, ShowView, useResourceDefinition } from 'react-admin';
import RealtimeShowContextProvider from '../../../jsonapi/components/Realtime/RealtimeShowContextProvider';
import useSparseFieldsForOperation from '../../../jsonapi/hooks/useSparseFieldsForOperation';
import HarvestingJobActions from './HarvestingJobActions';
import HarvestingJobAside from './HarvestingJobAside';
import HarvestingJobTabbedShowLayout from './HarvestingJobTabbedShowLayout';


export const isStale = (timestamp: number, record: RaRecord) => {
  const stateTime = new Date(timestamp).getTime()
  const nowTime = new Date(Date.now()).getTime()
  if (['completed', 'aborted'].includes(record?.phase) ) return false;

  if (nowTime - stateTime > 10){
    return true
  }

  return false
}

const ShowHarvestingJob = () => {
    const { name } = useResourceDefinition()
    const { sparseFields: harvestingJobSparseFields } = useSparseFieldsForOperation(`list_${name}`)
    
    const sparseFields = useMemo(()=> {
      // see issue in drf-spectacular-json-api: https://github.com/jokiefer/drf-spectacular-json-api/issues/30
      // Therefore we need to implement this workaround to get all possible sparefield values
      return {
        ...harvestingJobSparseFields,
      }
    }, [harvestingJobSparseFields])

    const excludeSparseFields: any = useMemo(()=>({
      "HarvestingJob": [
        "temporaryMdMetadataFiles",
        "harvestedDatasetMetadata",
        "harvestedServiceMetadata",
      ]
    }),[])
   
    const sparseFieldsParams = useMemo(()=>{
      const _sparseFieldsParams: any = {}
      for (const [key, value] of Object.entries(sparseFields)) {
        if (key in excludeSparseFields){
          const excludeFields = excludeSparseFields[`${key}`]
          const filteredSparseFields = value.filter(fieldName => !excludeFields.includes(fieldName))
          // Hint: there is a bug in django json:api package where sparse fields parameter are not camelCase translated correctly.
          // For that we need to transform the values to snake case
          _sparseFieldsParams[`fields[${key}]`] = filteredSparseFields.map(field => snakeCase(field)).join(',')
        }
      }
      return _sparseFieldsParams
    },[sparseFields, excludeSparseFields ])

    return (
      <RealtimeShowContextProvider
        isStaleCheckInterval={5}
        isStale={isStale}
        queryOptions={{
          meta: {
            jsonApiParams:{
              include: 'service',
              'fields[CatalogueService]': 'id',
              ...sparseFieldsParams

            },
          }
        }}
      >
        <ShowView
          aside={<HarvestingJobAside />}
          actions={<HarvestingJobActions/>
          }
        >
          <HarvestingJobTabbedShowLayout />
        </ShowView>
      </RealtimeShowContextProvider>
    )
};

export default ShowHarvestingJob