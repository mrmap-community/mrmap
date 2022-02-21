import React from 'react';
import RepoTable from '../Shared/RepoTable/NewRepoTable';



const DatasetMetadataTable = (): JSX.Element => {
  return <RepoTable resourceTypes={['DatasetMetadata']} />;
};

export default DatasetMetadataTable;
