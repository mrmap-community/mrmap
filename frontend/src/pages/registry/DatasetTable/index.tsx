import SchemaTable from '@/components/SchemaTable';
import { PageContainer } from '@ant-design/pro-layout';
import type { ReactElement } from 'react';

const DatasetTable = (): ReactElement => {
  return (
    <PageContainer>
      <SchemaTable 
        resourceTypes={{baseResourceType: 'DatasetMetadata'}} 
      />
    </PageContainer>
  );
};

export default DatasetTable;
