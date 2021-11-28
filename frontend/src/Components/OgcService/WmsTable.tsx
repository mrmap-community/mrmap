import React from 'react';

import WmsRepo from '../../Repos/WmsRepo';
import ResourceTable from '../Shared/ResourceTable';

const repo = new WmsRepo();

export const WmsTable = (): JSX.Element => {
  return <ResourceTable repo={repo} addRecord='/registry/services/add'/>;
};

export default WmsTable;
