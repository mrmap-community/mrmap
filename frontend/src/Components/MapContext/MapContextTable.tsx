import React from 'react';

import MapContextRepo from '../../Repos/MapContextRepo';
import ResourceTable from '../Shared/ResourceTable';

const repo = new MapContextRepo();

export const MapContextTable = (): JSX.Element => {
  return <ResourceTable repo={repo} addRecord='/registry/mapcontexts/add'/>;
};

export default MapContextTable;
