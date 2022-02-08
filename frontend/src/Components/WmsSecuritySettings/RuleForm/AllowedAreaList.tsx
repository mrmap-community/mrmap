import ProTable from '@ant-design/pro-table';
import { useMap } from '@terrestris/react-geo';
import { DigitizeUtil } from '@terrestris/react-geo/dist/Util/DigitizeUtil';
import BaseEvent from 'ol/events/Event';
import { default as Geometry, default as OlGeometry } from 'ol/geom/Geometry';
import VectorSource from 'ol/source/Vector';
import { default as React, ReactElement, useEffect, useState } from 'react';

export const AllowedAreaList = (): ReactElement => {

  const map = useMap();
  const [dataSource, setDataSource] = useState([] as any[]);

  const onAreaSourceChanged = (source: VectorSource<Geometry>, event: BaseEvent|Event) => {
    const newDataSource:any [] = [];
    let i = 1;
    source.getFeatures().forEach ( (feature) => {
      newDataSource.push ({
        key: String (i),
        name: `Polygon ${i}`,
        feature: feature
      });
      i++;
    });
    setDataSource(newDataSource);
  };

  useEffect ( () => {
    const layer = DigitizeUtil.getDigitizeLayer(map);
    const source = layer.getSource();
    const handler = onAreaSourceChanged.bind(null, source);
    source.on ('change', handler);
    return ( () => {
      source.un ('change', handler);
    });
  },[map]);

  const columns = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
    }
  ];

  return (
    <>
      {
        <ProTable
          bordered={true}
          cardBordered={true}
          columns={columns}
          dataSource={dataSource}
          showHeader={false}
          pagination={false}
          search={false}
          options={false}
          toolBarRender={false}
          onRow={(record, rowIndex) => {
            return {
              onClick: event => {
                const geom: OlGeometry = record.feature.getGeometry();
                map.getView().fit(geom.getExtent());
              }
            };
          }}          
        />
      }
    </>);
};
