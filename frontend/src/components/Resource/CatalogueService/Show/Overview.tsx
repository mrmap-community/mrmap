import { createElement, Fragment, useMemo } from 'react';
import { Loading, SimpleShowLayout, useRecordContext, useResourceDefinition } from 'react-admin';
import { useFieldsForOperation } from '../../../../jsonapi/hooks/useFieldsForOperation';
import { createElementIfDefined } from '../../../../utils';
import SimpleCard from '../../../MUI/SimpleCard';
import ListHarvestingJob from '../../HarvestingJob/ListHarvestingJob';
import ListPeriodicHarvestingJob from '../../PeriodicHarvestingJob/ListPeriodicHarvestingJob';
import HarvestingDailyStatsChart from '../HarvestingDailyStatsChart';


export interface OverviewProps {
  sources?: string[]
}

const Overview = ({
  sources = ['id', 'title', 'abstract']
}: OverviewProps) => {

  const record = useRecordContext();

  const { name: cswName, icon: cswIcon } = useResourceDefinition({resource: 'CatalogueService'})
  const { name: HarvestingJobName, icon: HarvestingJobIcon } = useResourceDefinition({resource: 'HarvestingJob'})
  const { name: periodicHarvestingJobName, icon: periodicHarvestingJobIcon } = useResourceDefinition({resource: 'PeriodicHarvestingJob'})

  const fieldDefinitions = useFieldsForOperation({operationId:'retrieve_CatalogueService', forInput:false, ignoreId:false});
  const fields = useMemo(
    () => 
      sources.map(
        source => {
          const fieldDefinition = fieldDefinitions.find(fieldDefinition => fieldDefinition.props.source === source)
          if (fieldDefinition === undefined){
            return <Fragment></Fragment>
          }
          return createElement(
            fieldDefinition.component, 
            {
              ...fieldDefinition.props, 
              key: `${fieldDefinition.props.source}-${record?.id}`,
            }
          )
        }
      )
    ,[fieldDefinitions]
  )

  if (record === undefined){
    return <Loading/>
  }

  return (
  <Fragment>
    <SimpleCard
      title={<span>{createElementIfDefined(cswIcon)} {cswName}</span>}
    >
      <SimpleShowLayout>
        {...fields}
      </SimpleShowLayout>
    </SimpleCard>
    <SimpleCard
      title={<span>{createElementIfDefined(HarvestingJobIcon)} {HarvestingJobName}</span>}
    >
      <HarvestingDailyStatsChart resource='HarvestedMetadataRelation' filter={{ 'service': record.id }} />
      <ListHarvestingJob />
    </SimpleCard>
    <SimpleCard
      title={<span>{createElementIfDefined(periodicHarvestingJobIcon)} {periodicHarvestingJobName}</span>}
    >
      <ListPeriodicHarvestingJob/>
    </SimpleCard>
  </Fragment>
  )

}

export default Overview;