import React from 'react';

import WfsRepo from '../../Repos/WfsRepo';
import RepoTable from '../Shared/Table/RepoTable';

const repo = new WfsRepo();

export const WfsTable = (): JSX.Element => {
  return <RepoTable repo={repo} addRecord='/registry/services/add'/>;
};

export default WfsTable;
