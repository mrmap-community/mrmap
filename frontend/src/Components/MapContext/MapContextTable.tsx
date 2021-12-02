import React from 'react';
import { useNavigate } from 'react-router';

import MapContextRepo from '../../Repos/MapContextRepo';
import ResourceTable from '../Shared/ResourceTable';

const repo = new MapContextRepo();

export const MapContextTable = (): JSX.Element => {
  const navigate = useNavigate();

  return (
  <ResourceTable
    repo={repo}
    editRecord
    onEditRecord={() => navigate('/registry/mapcontexts/edit')}
    addRecord='/registry/mapcontexts/add'
  />);
};

export default MapContextTable;
