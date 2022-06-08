import type { TreeNode } from '@/components/RessourceDetails/OgcServiceDetails';
import OgcServiceDetails from '@/components/RessourceDetails/OgcServiceDetails';
import type { JsonApiDocument, JsonApiPrimaryData } from '@/utils/jsonapi';
import { getIncludesByType } from '@/utils/jsonapi';
import type { ParamsArray } from 'openapi-client-axios';
import type { ReactElement } from 'react';

const transformTreeData = (wfs: JsonApiDocument): TreeNode[] => {
  return getIncludesByType(wfs, 'FeatureType').map((node) => {
    return {
      key: node.id,
      title: node.attributes.stringRepresentation,
      raw: node,
      isLeaf: true,
    };
  });
};

const transformFlatNodeList = (wfs: JsonApiDocument): JsonApiPrimaryData[] => {
  return getIncludesByType(wfs, 'FeatureType');
};

const WfsDetails = (): ReactElement => {
  /**
   * derived constants
   */
  const getWebFeatureServiceParams: ParamsArray = [
    {
      in: 'query',
      name: 'include',
      value: 'featuretypes',
    },
    {
      in: 'query',
      name: 'fields[FeatureType]',
      value: 'string_representation,is_active,dataset_metadata',
    },
  ];

  return (
    <OgcServiceDetails
      resourceType="WebFeatureService"
      additionalGetRessourceParams={getWebFeatureServiceParams}
      nodeRessourceType={'FeatureType'}
      transformTreeData={transformTreeData}
      transformFlatNodeList={transformFlatNodeList}
    />
  );
};

export default WfsDetails;
