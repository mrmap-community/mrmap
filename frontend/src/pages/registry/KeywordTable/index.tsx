import PageContainer from '@/components/PageContainer';
import SchemaTable from '@/components/SchemaTable';
import type { ReactElement } from 'react';

const KeywordTable = (): ReactElement => {
  return (
    <PageContainer>
      <SchemaTable 
        resourceTypes={{baseResourceType: 'Keyword'}} 
      />
    </PageContainer>
  );
};

export default KeywordTable;
