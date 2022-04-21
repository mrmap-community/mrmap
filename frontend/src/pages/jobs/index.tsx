import SchemaTable from '@/components/SchemaTable';
import { PageContainer } from '@ant-design/pro-layout';
import type { ReactElement } from 'react';

const BackgroundProcessesTable = (): ReactElement => {
  return (
    <PageContainer>
      <SchemaTable resourceTypes={['BackgroundProcess']} />
    </PageContainer>
  );
};

export default BackgroundProcessesTable;
