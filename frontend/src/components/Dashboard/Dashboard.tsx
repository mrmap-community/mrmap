import { type ReactNode } from 'react';

import { Stack } from '@mui/material';

import ResourceListCard from './Cards/ResourceListCard';
import ServiceAttentionCard from './Cards/ServiceAttentionCard';
import WorkQueueCard from './Cards/WorkQueueCard';

const styles = {
  flex: { display: 'flex' },
  flexColumn: { display: 'flex', flexDirection: 'column' },
  leftCol: { flex: 1, marginRight: '0.5em' },
  rightCol: { flex: 1, marginLeft: '0.5em' },
  singleCol: { marginTop: '1em', marginBottom: '1em' },
};

const Spacer = () => <span style={{ width: '1em' }} />;

/**
 * The dashboard of the deployment.
 *
 * It answers the work before the inventory: what waits for an administrator,
 * which services carry a problem and which work the deployment is doing right
 * now are answered above the counts of the registered resources, because an
 * administrator opens this screen to decide what to do next and not to read the
 * size of the registry. The inventory stays below and is the same as before.
 */
const Dashboard = (): ReactNode => {
  return (
    <div style={styles.singleCol}>
      {/* the queues of work and the alerts of the services answer the work which
          waits - on a narrow screen they are asked one below the other */}
      <Stack spacing={2} sx={{ mb: 2 }}>
        <WorkQueueCard />
        <ServiceAttentionCard />
      </Stack>
      <div style={styles.singleCol}>
        <div style={styles.flex}>
          <ResourceListCard resource={'WebMapService'} withList={false}/>
          <Spacer />
          <ResourceListCard resource={'Layer'} withList={false}/>
          <Spacer/>
          <ResourceListCard resource={'WebFeatureService'} withList={false}/>
          <Spacer />
          <ResourceListCard resource={'FeatureType'} withList={false}/>
        </div>
      </div>
      <div style={styles.singleCol}>
        <div style={styles.flex}>
          <ResourceListCard resource={'CatalogueService'} withList={false} />
          <Spacer />
          <ResourceListCard resource={'DatasetMetadataRecord'} withList={false} />
          <Spacer />
          <ResourceListCard resource={'ServiceMetadataRecord'} withList={false} />
        </div>
      </div>
      <div style={styles.singleCol}>
        <div style={styles.flex}>
          <ResourceListCard resource={'Organization'} />
          <Spacer />
          <ResourceListCard resource={'User'} />
        </div>
      </div>
    </div>
  )
}

export default Dashboard
