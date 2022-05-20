import SchemaTable from '@/components/SchemaTable';
import { PageContainer } from '@ant-design/pro-layout';
import type { ReactElement } from 'react';
import { useIntl, useParams } from 'umi';

const LayerTable = (): ReactElement => {

  const intl = useIntl();
  const { id } = useParams<{ id: string }>();

  return (
    <PageContainer
      title={
        id ?
        intl.formatMessage(
          { id: 'menu.registry.wmsLayers' }, 
          { id: id}
        ) :
        intl.formatMessage(
          { id: 'menu.registry.layers' },
        )
      }
      
    >
      <SchemaTable 
        resourceTypes={{baseResourceType: 'Layer'}} 
      />
    </PageContainer>
  );
};

export default LayerTable;
