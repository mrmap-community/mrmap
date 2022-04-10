import SchemaTable from '@/components/SchemaTable';
import { Button } from 'antd';
import type { ReactElement } from 'react';

export const SearchTable = ({
  addDatasetToMapAction = () => undefined,
}: {
  addDatasetToMapAction?: (dataset: any) => void;
}): ReactElement => {
  const getDatasetMetadataColumnActions = (text: any, record: any) => {
    const relatedLayers = record.relationships?.selfPointingLayers?.data;
    return (
      <>
        <Button
          disabled={!relatedLayers || relatedLayers.length === 0}
          size="small"
          type="primary"
          onClick={() => {
            addDatasetToMapAction(record);
          }}
        >
          Zur Karte hinzufügen
        </Button>
      </>
    );
  };

  return (
    <SchemaTable
      resourceTypes={['DatasetMetadata']}
      // columns={datasetMetadataColumns}
      toolBarRender={false}
      size="small"
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
          xmlBackupFile: { show: false },
        },
      }}
    />
  );
};
