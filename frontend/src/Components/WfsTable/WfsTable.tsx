import React from 'react';
import RepoTable from '../Shared/RepoTable/NewRepoTable';



const WfsTable = (): JSX.Element => {
  return (
    <RepoTable 
      resourceType='WebFeatureService' 
      onAddRecord='/registry/services/wfs/add'
    />
  );
};

export default WfsTable;
