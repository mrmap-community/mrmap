import ProTable from '@ant-design/pro-table';
import { default as React, ReactElement } from 'react';


export const AllowedAreaList = (): ReactElement => {

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
        toolBarRender={false}
      />
    </>);
};
