import React from 'react';

import { useNavigate } from 'react-router';

import MapContextRepo from '../../Repos/MapContextRepo';
import RepoTable from '../Shared/RepoTable/RepoTable';


const repo = new MapContextRepo();

const MapContextTable = (): JSX.Element => {
  const navigate = useNavigate();

  return (
    <RepoTable
      repo={repo}
      onAddRecord='/registry/mapcontexts/add'
      onEditRecord={(mapContextId) => navigate(`/registry/mapcontexts/${mapContextId}/edit`)}
    />);
};

export default MapContextTable;
