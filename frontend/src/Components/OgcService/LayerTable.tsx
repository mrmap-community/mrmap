import React from 'react';
import LayerRepo from '../../Repos/LayerRepo';
import RepoTable from '../Shared/Table/RepoTable';


const repo = new LayerRepo();

const LayerTable = (): JSX.Element => {
  return <RepoTable repo={repo} />;
};

export default LayerTable;
