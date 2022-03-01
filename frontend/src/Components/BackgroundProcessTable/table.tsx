import React from 'react';
import RepoTable from '../Shared/RepoTable/NewRepoTable';


const BackgroundProcessTable = (): JSX.Element => {
  
  return <RepoTable
    resourceTypes={['BackgroundProcess']}
  />;
};

export default BackgroundProcessTable;
