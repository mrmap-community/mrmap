import React from 'react';
import FeatureTypeRepo from '../../Repos/FeatureTypeRepo';
import RepoTable from '../Shared/RepoTable/RepoTable';


const repo = new FeatureTypeRepo();

const FeatureTypeTable = (): JSX.Element => {
  return <RepoTable repo={repo} />;
};

export default FeatureTypeTable;
