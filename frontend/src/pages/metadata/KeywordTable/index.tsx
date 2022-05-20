import PageContainer from '@/components/PageContainer';
import SchemaTable from '@/components/SchemaTable';
import type { ReactElement } from 'react';

const KeywordTable = (): ReactElement => {
  console.log('huhu');
  return (
    <PageContainer
      menuPaths={['metadata']}
    >
      <SchemaTable 
        resourceTypes={{baseResourceType: 'Keyword'}} 
      />
    </PageContainer>
  );
};

export default KeywordTable;
