import React from 'react';

import DatasetMetadataRepo from '../../Repos/DatasetMetadataRepo';
import ResourceTable from '../Shared/ResourceTable';

const repo = new DatasetMetadataRepo();

export const DatasetMetadataTable = (): JSX.Element => {
  return <ResourceTable repo={repo} />;
};

export default DatasetMetadataTable;
