import React from 'react';
import { useNavigate } from 'react-router';

import MapContextRepo from '../../Repos/MapContextRepo';
import RepoTable from '../Shared/Table/RepoTable';

const repo = new MapContextRepo();

export const MapContextTable = (): JSX.Element => {
  const navigate = useNavigate();

  return (
  <RepoTable
    repo={repo}
    onEditRecord={(mapContextId) => navigate(`/registry/mapcontexts/${mapContextId}/edit`)}
    addRecord='/registry/mapcontexts/add'
  />);
};

export default MapContextTable;
