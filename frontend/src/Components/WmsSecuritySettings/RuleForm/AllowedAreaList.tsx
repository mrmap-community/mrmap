import ProTable from '@ant-design/pro-table';
import { DigitizeButton, ToggleGroup, useMap } from '@terrestris/react-geo';
import { default as React, ReactElement } from 'react';


export const AllowedAreaList = (): ReactElement => {

  const map = useMap();

  const dataSource = [
    {
      key: '1',
      name: 'Polygon 1',
    },
    {
      key: '2',
      name: 'Polygon 2',
    },
  ];
  
  const columns = [
    {
      title: 'Name',
      dataIndex: 'name',
      key: 'name',
    }
  ];

  return (
    <>
      <ProTable
        bordered={true}
        cardBordered={true}
        columns={columns}
        dataSource={dataSource}
        showHeader={false}
        pagination={false}
        search={false}
        options={false}
        toolBarRender={ () => [
          <ToggleGroup key='toggle'>
            <DigitizeButton
              name='drawRectangle'
              map={map}
              drawType='Rectangle'
            >
            Add rectangle
            </DigitizeButton>
            <DigitizeButton
              name='drawPolygon'
              map={map}
              drawType='Polygon'
            >
            Add polygon
            </DigitizeButton>
            <DigitizeButton
              name='edit'
              map={map}
              editType='Edit'
            >
            Edit
            </DigitizeButton>          
            <DigitizeButton
              name='delete'
              map={map}
              editType='Delete'
            >
            Delete
            </DigitizeButton>
          </ToggleGroup>
        ]}
      />
    </>);
};
