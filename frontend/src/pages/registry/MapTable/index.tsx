import SchemaTable from '@/components/SchemaTable';
import { PageContainer } from '@ant-design/pro-layout';
import type { ReactElement } from 'react';
import { history } from 'umi';

const MapTable = (): ReactElement => {
  return (
    <PageContainer>
      <SchemaTable
        resourceTypes={{baseResourceType: 'MapContext'}}
        onAddRecord={() => history.push('/registry/maps/add')}
        onEditRecord={(mapId) => history.push(`/registry/maps/${mapId}/edit`)}
      />
    </PageContainer>
  );
};

export default MapTable;
