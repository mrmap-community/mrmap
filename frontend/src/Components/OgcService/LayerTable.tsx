import React from 'react';

import LayerRepo from '../../Repos/LayerRepo';
import ResourceTable from '../Shared/ResourceTable';

const repo = new LayerRepo();

export const LayerTable = (): JSX.Element => {
  return <ResourceTable repo={repo} />;
};

export default LayerTable;
