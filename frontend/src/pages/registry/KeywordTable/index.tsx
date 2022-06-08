import GenericPageContainer from '@/components/PageContainer';
import SchemaTable from '@/components/SchemaTable';
import type { ReactElement } from 'react';

const KeywordTable = (): ReactElement => {
  return (
    <GenericPageContainer>
      <SchemaTable resourceTypes={{ baseResourceType: 'Keyword' }} />
    </GenericPageContainer>
  );
};

export default KeywordTable;
