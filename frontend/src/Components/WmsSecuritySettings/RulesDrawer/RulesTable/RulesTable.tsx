import React, { ReactElement } from 'react';
import { useNavigate } from 'react-router-dom';
import WmsAllowedOperationRepo from '../../../../Repos/WmsAllowedOperationRepo';
import RepoTable from '../../../Shared/RepoTable/RepoTable';

export interface RulesTableProps {
  wmsId: string
}

export const RulesTable = ({
  wmsId
}:RulesTableProps): ReactElement => {
  const navigate = useNavigate();
  // no side effects, so useEffect is not needed here
  const repo = new WmsAllowedOperationRepo(wmsId);

  return (
    <RepoTable
      repo={repo}
      onAddRecord={`/registry/services/wms/${wmsId}/security/rules/add`}
      onEditRecord={(recordId) => navigate(`/registry/services/wms/${wmsId}/security/rules/${recordId}/edit`)}
    />
  );
};
