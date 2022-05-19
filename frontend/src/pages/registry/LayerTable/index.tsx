import SchemaTable from '@/components/SchemaTable';
import { PageContainer } from '@ant-design/pro-layout';
import type { ReactElement } from 'react';
import { useMemo } from 'react';
import { useParams } from 'umi';

const LayerTable = (): ReactElement => {


  const { id } = useParams<{ id: string }>();

  const resourceTypes = useMemo(() => {
    if (id){
      const pathname = window.location.pathname;
      const routes = pathname.split('/');
      const indexOfId = routes.indexOf(id);
      return {
        baseResourceType: routes[indexOfId+1],
        nestedResource: {
          id: id,
          type: routes[indexOfId-1]
        }
      };
    } else {
      return {baseResourceType: 'Layer'};
    }
  }, [id]);
   
  return (
    <PageContainer>
      <SchemaTable 
        resourceTypes={resourceTypes} 
      />
    </PageContainer>
  );
};

export default LayerTable;
