import React from 'react';
import RepoTable from '../Shared/RepoTable/NewRepoTable';



const WfsTable = (): JSX.Element => {
  return (
    <RepoTable 
      resourceTypes={['WebFeatureService']} 
    />
  );
};

export default WfsTable;
