import React from 'react';

import WfsRepo from '../../Repos/WfsRepo';
import RepoTable from '../Shared/Table/RepoTable';

const repo = new WfsRepo();

export const WfsTable = (): JSX.Element => {
  return <RepoTable repo={repo} />;
};

export default WfsTable;
