import SchemaTable from '@/components/SchemaTable';
import { PageContainer } from '@ant-design/pro-layout';
import type { ReactElement } from 'react';
import React from 'react';

const LayerTable = (): ReactElement => {
  return (
    <PageContainer>
      <SchemaTable resourceTypes={['Layer']} />
    </PageContainer>
  );
};

export default LayerTable;
