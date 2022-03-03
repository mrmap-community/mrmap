import React, { ReactElement } from 'react';
import { useNavigate } from 'react-router-dom';
import RepoTable from '../../../Shared/RepoTable/NewRepoTable';

export const RulesTable = ({
  wmsId,
}: {
  wmsId: string
}): ReactElement => {

  const navigate = useNavigate();

  return (
    <RepoTable
      resourceTypes={['AllowedWebMapServiceOperation', 'WebMapService']}
      nestedLookups={[{ name: 'parent_lookup_secured_service', value: wmsId, in: 'path' }]}
      options={{
        setting: false,
        density: false
      }}
      pagination={false}
      onAddRecord={() => navigate(`/registry/services/wms/${wmsId}/security/rules/add`)}
      onEditRecord={(recordId) => navigate(`/registry/services/wms/${wmsId}/security/rules/${recordId}/edit`)}
      search={false}
      columnsState={{
        value: {
          allowedArea: { show: false },
          id: { show: false },
          stringRepresentation: { show: false }
        }
      }}
    />
  );
};
