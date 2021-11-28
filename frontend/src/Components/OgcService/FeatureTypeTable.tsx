import React from 'react';

import FeatureTypeRepo from '../../Repos/FeatureTypeRepo';
import ResourceTable from '../Shared/ResourceTable';

const repo = new FeatureTypeRepo();

export const FeatureTypeTable = (): JSX.Element => {
  return <ResourceTable repo={repo} />;
};

export default FeatureTypeTable;
