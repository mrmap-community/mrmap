import SchemaTable from '@/components/SchemaTable';
import { PageContainer } from '@ant-design/pro-layout';
import type { ReactElement } from 'react';
import React from 'react';

const MapTable = (): ReactElement => {
  return (
    <PageContainer>
      <SchemaTable resourceTypes={['MapContext']} />
    </PageContainer>
  );
};

export default MapTable;
