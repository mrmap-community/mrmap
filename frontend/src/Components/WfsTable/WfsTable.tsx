import React from 'react';

import WfsRepo from '../../Repos/WfsRepo';
import RepoTable from '../Shared/RepoTable/RepoTable';


const repo = new WfsRepo();

const WfsTable = (): JSX.Element => {
  return (
    <RepoTable 
      repo={repo} 
      onAddRecord='/registry/services/wfs/add'
    />
  );
};

export default WfsTable;
