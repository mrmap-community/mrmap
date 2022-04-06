import SchemaTable from '@/components/SchemaTable';
import type { ReactElement } from 'react';
import React from 'react';
import { history } from 'umi';

export const RulesTable = ({ wmsId }: { wmsId: string }): ReactElement => {
  return (
    <SchemaTable
      resourceTypes={['AllowedWebMapServiceOperation', 'WebMapService']}
      nestedLookups={[{ name: 'parent_lookup_secured_service', value: wmsId, in: 'path' }]}
      options={{
        setting: false,
        density: false,
      }}
      pagination={false}
      onAddRecord={() => history.push(`/registry/services/wms/${wmsId}/security/rules/add`)}
      onEditRecord={(recordId: string | number) =>
        history.push(`/registry/services/wms/${wmsId}/security/rules/${recordId}/edit`)
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
