import { type ReactNode } from 'react';
import ResourceListCard from './Cards/ResourceListCard';
const styles = {
  flex: { display: 'flex' },
  flexColumn: { display: 'flex', flexDirection: 'column' },
  leftCol: { flex: 1, marginRight: '0.5em' },
  rightCol: { flex: 1, marginLeft: '0.5em' },
  singleCol: { marginTop: '1em', marginBottom: '1em' },
};

const Spacer = () => <span style={{ width: '1em' }} />;

const Dashboard = (): ReactNode => {
  return (
    <div style={styles.singleCol}>
      <div style={styles.singleCol}>
        <div style={styles.flex}>
          <ResourceListCard resource={'WebMapService'} withList={false}/>
          <Spacer />
          <ResourceListCard resource={'Layer'} withList={false}/>
        </div>
      </div>
      <div style={styles.singleCol}>
        <div style={styles.flex}>
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
