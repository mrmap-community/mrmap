import React from 'react';
import RepoTable from '../Shared/RepoTable/NewRepoTable';



const FeatureTypeTable = (): JSX.Element => {
  return <RepoTable resourceTypes={['FeatureType']} />;
};

export default FeatureTypeTable;
