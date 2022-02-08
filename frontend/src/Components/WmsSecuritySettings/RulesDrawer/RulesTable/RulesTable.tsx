import React, { ReactElement } from 'react';
import { useNavigate } from 'react-router-dom';
import WmsAllowedOperationRepo from '../../../../Repos/WmsAllowedOperationRepo';
import RepoTable, { RepoTableColumnType } from '../../../Shared/RepoTable/RepoTable';

export interface RulesTableProps {
  wmsId: string,
  setSelectedLayerIds: (ids: string[]) => void,
  setIsRuleEditingActive: (isActive: boolean) => void  
}

export const RulesTable = ({
  wmsId,
  setSelectedLayerIds,
  setIsRuleEditingActive  
}: RulesTableProps): ReactElement => {

  setIsRuleEditingActive(false);
  
  const navigate = useNavigate();
  // no side effects, so useEffect is not needed here
  const repo = new WmsAllowedOperationRepo(wmsId);

  const columns: RepoTableColumnType[] = [{
    dataIndex: 'description',
    title: 'Beschreibung',
    sorter: false
  },{
    dataIndex: 'id',
    hideInTable: true
  },{
    dataIndex: 'is_accessible',
    hideInTable: true
  },{
    dataIndex: 'allowed_area',
    hideInTable: true
  }];

  return (
    <>
      <RepoTable
        repo={repo}
        columns={columns}
        options={{
          setting: false,
          density: false
        }}
        pagination={false}
        onAddRecord={`/registry/services/wms/${wmsId}/security/rules/add`}
        onEditRecord={(recordId) => navigate(`/registry/services/wms/${wmsId}/security/rules/${recordId}/edit`)}
      />
    </>
  );
};
