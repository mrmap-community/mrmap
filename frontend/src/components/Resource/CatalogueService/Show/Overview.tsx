import { createElement, useMemo } from 'react';
import { SimpleShowLayout, useResourceDefinition } from 'react-admin';
import { useParams } from 'react-router-dom';
import ListGuesser from '../../../../jsonapi/components/ListGuesser';
import { useFieldsForOperation } from '../../../../jsonapi/hooks/useFieldsForOperation';
import { createElementIfDefined } from '../../../../utils';
import EmptyList from '../../../Lists/Empty';
import SimpleCard from '../../../MUI/SimpleCard';
import ListHarvestingJob from '../../HarvestingJob/ListHarvestingJob';
import HarvestingDailyStatsChart from '../HarvestingDailyStatsChart';


export interface OverviewProps {
  sources?: string[]
}

const Overview = ({
  sources = ['id', 'title', 'abstract']
}: OverviewProps) => {


  const { id } = useParams()
  const { name: cswName, icon: cswIcon } = useResourceDefinition({resource: 'CatalogueService'})
  const { name: HarvestingJobName, icon: HarvestingJobIcon } = useResourceDefinition({resource: 'HarvestingJob'})
  const { name: periodicHarvestingJobName, icon: periodicHarvestingJobIcon } = useResourceDefinition({resource: 'PeriodicHarvestingJob'})

  const fieldDefinitions = useFieldsForOperation('retrieve_CatalogueService', false, false);
  const fields = useMemo(
    () => 
      sources.map(
        source => {
          const fieldDefinition = fieldDefinitions.find(fieldDefinition => fieldDefinition.props.source === source)
          if (fieldDefinition === undefined){
            return <></>
          }
          return createElement(
            fieldDefinition.component, 
            {
              ...fieldDefinition.props, 
              key: `${fieldDefinition.props.source}-${id}`,
            }
          )
        }
      )
    ,[fieldDefinitions]
  )

  return (
  <>
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
      <HarvestingDailyStatsChart resource='HarvestedMetadataRelation' filter={{ 'harvesting_job__service': id }} />
      <ListHarvestingJob />
    </SimpleCard>
    <SimpleCard
      title={<span>{createElementIfDefined(periodicHarvestingJobIcon)} {periodicHarvestingJobName}</span>}
    >
      <ListGuesser
        resource='PeriodicHarvestingJob'
        relatedResource='CatalogueService'
        empty={<EmptyList defaultValue={{ service: { id: id } }} />} />
    </SimpleCard>
  </>
  )

}

export default Overview;