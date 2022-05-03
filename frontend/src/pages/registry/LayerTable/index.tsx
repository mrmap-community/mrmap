import SchemaTable from '@/components/SchemaTable';
import { PageContainer } from '@ant-design/pro-layout';
import type { ReactElement } from 'react';

const LayerTable = (): ReactElement => {
  return (
    <PageContainer>
      <SchemaTable 
        resourceTypes={{baseResourceType: 'Layer'}} 
      />
    </PageContainer>
  );
};

export default LayerTable;
