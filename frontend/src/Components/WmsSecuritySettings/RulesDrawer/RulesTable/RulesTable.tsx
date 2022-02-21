import React, { ReactElement } from 'react';
import { useNavigate } from 'react-router-dom';
import RepoTable, { RepoTableColumnType } from '../../../Shared/RepoTable/NewRepoTable';

export const RulesTable = ({
  wmsId,
}: {
  wmsId: string
}): ReactElement => {

  const navigate = useNavigate();

  const columns: RepoTableColumnType[] = [{
    dataIndex: 'description',
    title: 'Beschreibung',
    sorter: false
  },{
    dataIndex: 'id',
    hideInTable: true
  },{
    dataIndex: 'isAccessible',
    hideInTable: true
  },{
    dataIndex: 'allowedArea',
    hideInTable: true
  }];

  return (   
    <RepoTable
      resourceTypes={['AllowedWebMapServiceOperation', 'WebMapService']}
      nestedLookups={[{ name: 'parent_lookup_secured_service', value: wmsId, in: 'path' }]}
      columns={columns}
      options={{
        setting: false,
        density: false
      }}
      pagination={false}
      onAddRecord={() => navigate(`/registry/services/wms/${wmsId}/security/rules/add`)}
      onEditRecord={(recordId) => navigate(`/registry/services/wms/${wmsId}/security/rules/${recordId}/edit`)}
    />
  );
};
