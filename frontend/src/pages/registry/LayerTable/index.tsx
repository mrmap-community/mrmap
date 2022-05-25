import GenericPageContainer from '@/components/PageContainer';
import SchemaTable from '@/components/SchemaTable';
import type { ReactElement } from 'react';

const LayerTable = (): ReactElement => {

  return (
    <GenericPageContainer>
      <SchemaTable 
        resourceTypes={{baseResourceType: 'Layer'}} 
      />
    </GenericPageContainer>
  );
};

export default LayerTable;
