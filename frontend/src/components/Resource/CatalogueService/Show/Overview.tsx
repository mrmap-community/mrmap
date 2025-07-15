import { SimpleShowLayout, TextField, useResourceDefinition } from 'react-admin';
import { useParams } from 'react-router-dom';
import ListGuesser from '../../../../jsonapi/components/ListGuesser';
import { createElementIfDefined } from '../../../../utils';
import EmptyList from '../../../Lists/Empty';
import SimpleCard from '../../../MUI/SimpleCard';
import ListHarvestingJob from '../../HarvestingJob/ListHarvestingJob';
import HarvestingDailyStatsChart from '../HarvestingDailyStatsChart';


const Overview = () => {


  const { id } = useParams()
  const { name: cswName, icon: cswIcon } = useResourceDefinition({resource: 'CatalogueService'})
  const { name: HarvestingJobName, icon: HarvestingJobIcon } = useResourceDefinition({resource: 'HarvestingJob'})
  const { name: periodicHarvestingJobName, icon: periodicHarvestingJobIcon } = useResourceDefinition({resource: 'PeriodicHarvestingJob'})


return (
  <>
    <SimpleCard
      title={<span>{createElementIfDefined(cswIcon)} {cswName}</span>}
    >
      <SimpleShowLayout>
        <TextField source="id" />
        <TextField source="title" />
        <TextField source="abstract" />
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