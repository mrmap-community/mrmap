import { zoomTo } from '@/utils/map';
import { useMap } from '@terrestris/react-geo';
import { DigitizeUtil } from '@terrestris/react-geo/dist/Util/DigitizeUtil';
import { Table } from 'antd';
import type Feature from 'ol/Feature';
import type { default as Geometry } from 'ol/geom/Geometry';
import type VectorSource from 'ol/source/Vector';
import type { ReactElement } from 'react';
import { useEffect, useState } from 'react';

interface Area {
  key: string;
  name: string;
  feature: Feature<Geometry>;
}

export const AllowedAreaTable = (): ReactElement => {
  const map = useMap();
  const [dataSource, setDataSource] = useState<Area[]>([]);

  const onAreaSourceChanged = (source: VectorSource<Geometry>) => {
    const newDataSource: Area[] = [];
    let i = 1;
    source.getFeatures().forEach((feature) => {
      newDataSource.push({
        key: String(i),
        name: `Polygon ${i}`,
        feature: feature,
      });
      i++;
    });
    setDataSource(newDataSource);
  };

  useEffect(() => {
    if (map) {
      const layer = DigitizeUtil.getDigitizeLayer(map);
      const source = layer.getSource();
      if (source) {
        const handler = onAreaSourceChanged.bind(null, source);
        source.on('change', handler);
        return () => {
          source.un('change', handler);
        };
      }
    }
    return undefined;
  }, [map]);

  const columns = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
    },
  ];

  return (
    <Table
      bordered={true}
      columns={columns}
      dataSource={dataSource}
      showHeader={false}
      pagination={false}
      onRow={(record) => {
        return {
          onClick: () => {
            if (map) {
              zoomTo(map, record.feature);
            }
          },
        };
      }}
    />
  );
};
