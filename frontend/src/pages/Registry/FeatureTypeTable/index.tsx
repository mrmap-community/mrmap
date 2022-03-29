import SchemaTable from '@/components/SchemaTable';
import { PageContainer } from '@ant-design/pro-layout';
import type { ReactElement } from 'react';
import React from 'react';

const FeatureTypeTable = (): ReactElement => {
  return (
    <PageContainer>
      <SchemaTable resourceTypes={['FeatureType']} />
    </PageContainer>
  );
};

export default FeatureTypeTable;
