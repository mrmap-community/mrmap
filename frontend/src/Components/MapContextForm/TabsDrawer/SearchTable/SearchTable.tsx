import { Button } from 'antd';
import React, { ReactElement, ReactNode } from 'react';
import RepoTable, { RepoTableColumnType } from '../../../Shared/RepoTable/NewRepoTable';
import { buildSearchTransformText } from '../../../Shared/RepoTable/TableHelper';


const getDatasetMetadataColumns = 
  (renderActions: (text: any, record:any) => ReactNode): RepoTableColumnType[] => [{
    dataIndex: 'title',
    title: 'Titel',
    // disable rendering by return null in renderFormItem, because we cannot set 'hideInSearch: true' for
    // every data column (otherwise our custom search field would not be rendered by the antd Pro Table)
    renderFormItem: () => {
      return null;
    }
    // hideInSearch: true
  }, {
    dataIndex: 'abstract',
    title: 'Zusammenfassung',
    hideInSearch: true
  }, {
    dataIndex: 'id',
    hideInTable: true
  }, {
    dataIndex: 'xmlBackupFile',
    hideInTable: true
  }, {
    dataIndex: 'accessConstraints',
    hideInTable: true
  }, {
    dataIndex: 'fees',
    hideInTable: true
  }, {
    dataIndex: 'useLimitation',
    hideInTable: true
  }, {
    dataIndex: 'fileIdentifier',
    hideInTable: true
  }, {
    dataIndex: 'licenseSourceNote',
    hideInTable: true
  }, {
    dataIndex: 'dateStamp',
    hideInTable: true
  }, {
    dataIndex: 'origin',
    hideInTable: true
  }, {
    dataIndex: 'originUrl',
    hideInTable: true
  }, {
    dataIndex: 'isBroken',
    hideInTable: true
  }, {
    dataIndex: 'isCustomized',
    hideInTable: true
  }, {
    dataIndex: 'insufficientQuality',
    hideInTable: true
  }, {
    dataIndex: 'isSearchable',
    hideInTable: true
  }, {
    dataIndex: 'hits',
    hideInTable: true
  }, {
    dataIndex: 'spatialResType',
    hideInTable: true
  }, {
    dataIndex: 'spatialResValue',
    hideInTable: true
  }, {
    dataIndex: 'format',
    hideInTable: true
  }, {
    dataIndex: 'charset',
    hideInTable: true
  }, {
    dataIndex: 'inspireTopConsistence',
    hideInTable: true
  }, {
    dataIndex: 'previewImage',
    hideInTable: true
  }, {
    dataIndex: 'lineageStatement',
    hideInTable: true
  }, {
    dataIndex: 'updateFrequencyCode',
    hideInTable: true
  }, {
    dataIndex: 'boundingGeometry',
    hideInTable: true
  }, {
    dataIndex: 'datasetId',
    hideInTable: true
  }, {
    dataIndex: 'datasetIdCodeSpace',
    hideInTable: true
  }, {
    dataIndex: 'inspireInteroperability',
    hideInTable: true
  }, {
    key: 'actions',
    title: 'Aktionen',
    valueType: 'option',
    render: renderActions
  }, {
    dataIndex: 'search',
    title: 'Suchbegriffe',
    valueType: 'text',
    hideInTable: true,
    hideInSearch: false,
    search : {
      transform : buildSearchTransformText('search')
    }
  },
  {
    dataIndex: 'isAccessible',
    hideInTable: true
  }
  ];

export const SearchTable = ({
  addDatasetToMapAction = () => undefined,
}:{
  addDatasetToMapAction?: (dataset: any) => void;
}): ReactElement => {

  const getDatasetMetadataColumnActions = (text: any, record:any) => {
    return (
      <>
        <Button
          disabled={record.layers.length === 0 || !record.layers}
          size='small'
          type='primary'
          onClick={ () => { addDatasetToMapAction(record); } }
        >
            Zur Karte hinzufügen
        </Button>
      </>
    );
  };
    
  const datasetMetadataColumns = getDatasetMetadataColumns(getDatasetMetadataColumnActions);

  return (
    <RepoTable
      resourceTypes={['DatasetMetadata']}
      columns={datasetMetadataColumns}
      
    />
  );
};
