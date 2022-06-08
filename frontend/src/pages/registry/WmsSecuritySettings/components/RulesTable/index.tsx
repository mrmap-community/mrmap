import SchemaTable from '@/components/SchemaTable';
import type { ReactElement } from 'react';
import { history } from 'umi';

const RulesTable = ({ wmsId }: { wmsId: string }): ReactElement => {
  return (
    <SchemaTable
      resourceTypes={{
        baseResourceType: 'AllowedWebMapServiceOperation',
        nestedResource: { type: 'WebMapService', id: wmsId },
      }}
      options={{
        setting: false,
        density: false,
      }}
      pagination={false}
      onAddRecord={() => history.push(`/registry/wms/${wmsId}/security/rules/add`)}
      onEditRecord={(recordId: string | number) =>
        history.push(`/registry/wms/${wmsId}/security/rules/${recordId}/edit`)
      }
      search={false}
      columnsState={{
        value: {
          allowedArea: { show: false },
          id: { show: false },
          stringRepresentation: { show: false },
        },
      }}
    />
  );
};

export default RulesTable;
