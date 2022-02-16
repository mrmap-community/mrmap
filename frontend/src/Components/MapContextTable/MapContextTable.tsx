import React from 'react';
import { useNavigate } from 'react-router';
import RepoTable from '../Shared/RepoTable/NewRepoTable';



const MapContextTable = (): JSX.Element => {
  const navigate = useNavigate();

  return (
    <RepoTable
      resourceType='MapContext'
      onAddRecord='/registry/mapcontexts/add'
      onEditRecord={(mapContextId) => navigate(`/registry/mapcontexts/${mapContextId}/edit`)}
    />);
};

export default MapContextTable;
