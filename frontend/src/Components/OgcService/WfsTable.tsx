import React from 'react';

import WfsRepo from '../../Repos/WfsRepo';
import ResourceTable from '../Shared/ResourceTable';

const repo = new WfsRepo();

export const WfsTable = (): JSX.Element => {
  return <ResourceTable repo={repo} addRecord='/registry/services/add'/>;
};

export default WfsTable;
