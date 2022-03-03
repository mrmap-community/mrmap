import { Button } from 'antd';
import React, { ReactElement } from 'react';
import RepoTable from '../../Shared/RepoTable/NewRepoTable';


export const SearchTable = ({
  addDatasetToMapAction = () => undefined,
}:{
  addDatasetToMapAction?: (dataset: any) => void;
}): ReactElement => {

  const getDatasetMetadataColumnActions = (text: any, record:any) => {
    const layerIds = record.relationships?.selfPointingLayers?.data?.map((d:any) => d.id);
    return (
      <>
        <Button
          disabled={!layerIds || layerIds?.length === 0}
          size='small'
          type='primary'
          onClick={ () => { addDatasetToMapAction(record); } }
        >
            Zur Karte hinzufügen
        </Button>
      </>
    );
  };

  return (
    <RepoTable
      resourceTypes={['DatasetMetadata']}
      // columns={datasetMetadataColumns}
      toolBarRender={false}
      size='small'
      defaultActions={[]}
      additionalActions={getDatasetMetadataColumnActions}
      columnsState={{
        value: {
          title: { order: -10 },
          abstract: { order: -9 },
          dateStamp: { order: -8 },
          fees: { order: -7 },
          id: { show: false },
          boundingGeometry: { show: false },
          charset: { show: false },
          hits: { show: false },
          stringRepresentation: { show: false },
          xmlBackupFile: { show: false }
        }
      }}
    />
  );
};
