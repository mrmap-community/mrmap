import { SearchOutlined } from '@ant-design/icons';
import { Button, Card, Input, Modal, notification, Space, Table } from 'antd';
import React, { createRef, ReactElement, useEffect, useState } from 'react';
import Highlighter from 'react-highlight-words';
import { useNavigate } from 'react-router';

import OpenApiRepo from '../../Repos/OpenApiRepo';

interface ResourceTableProps {
    repo: OpenApiRepo
    addRecord?: string
}

interface TableState {
  page: number;
  pageSize: number;
  ordering: string;
  filters: any;
}

const getColumnSearchProps = (dataIndex: any): any => {
  const searchInput: any = createRef();
  let searchText = '';
  let searchedColumn: any = null;
  return {
    filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => {
      const handleSearch = (selectedKeys: any, confirm: any, dataIndex: any) => {
        confirm();
        searchText = selectedKeys[0];
        searchedColumn = dataIndex;
      };
      const handleReset = (clearFilters: any) => {
        clearFilters();
        searchText = '';
      };
      return (<div style={{ padding: 8 }}>
        <Input
          ref={searchInput}
          placeholder={`Search ${dataIndex}`}
          value={selectedKeys[0]}
          onChange={e => setSelectedKeys(e.target.value ? [e.target.value] : [])}
          onPressEnter={() => handleSearch(selectedKeys, confirm, dataIndex)}
          style={{ marginBottom: 8, display: 'block' }}
        />
        <Space>
          <Button
            type='primary'
            onClick={() => handleSearch(selectedKeys, confirm, dataIndex)}
            icon={<SearchOutlined />}
            size='small'
            style={{ width: 90 }}
          >
            Search
          </Button>
          <Button onClick={() => handleReset(clearFilters)} size='small' style={{ width: 90 }}>
            Reset
          </Button>
          <Button
            type='link'
            size='small'
            onClick={() => {
              confirm({ closeDropdown: false });
              searchText = selectedKeys[0];
              searchedColumn = dataIndex;
            }}
          >
            Filter
          </Button>
        </Space>
      </div>);
    },
    onFilterDropdownVisibleChange: (visible: any) => {
      if (visible) {
        setTimeout(() => searchInput.current.select(), 100);
      }
    },
    filterIcon: (filtered: any) => <SearchOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
    render: (text: any) => {
      return searchedColumn === dataIndex
        ? (
          <Highlighter
            highlightStyle={{ backgroundColor: '#ffc069', padding: 0 }}
            searchWords={[searchText]}
            autoEscape
            textToHighlight={text ? text.toString() : ''}
          />
          )
        : (
            text
          );
    }
  };
};

export const ResourceTable = ({ repo, addRecord }: ResourceTableProps): ReactElement => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState({
    dataSource: [],
    total: 0
  });
  const [tableState, setTableState] = useState<TableState>({
    page: 1,
    pageSize: 5,
    ordering: '',
    filters: {}
  });
  const [columns, setColumns] = useState<any>([]);
  const [columnTypes, setColumnTypes] = useState<any>({});

  const navigate = useNavigate();

  useEffect(() => {
    const onDeleteRecord = (record: any) => {
      async function deleteRecord () {
        await repo.delete(record.id);
        notification.success({
          message: 'Record deleted',
          description: `Record with id ${record.id} has been deleted succesfully`
        });
        // const newData = {
        //     dataSource: data.dataSource.filter((row: any) => (row.id !== record.id)),
        //     total: data.total - 1
        // };
        // setData(newData);
      }
      const modal = Modal.confirm({
        title: 'Delete record',
        content: `Do you want to delete the record with id ${record.id}?`,
        onOk: () => {
          modal.update(prevConfig => ({
            ...prevConfig,
            confirmLoading: true
          }));
          deleteRecord();
        }
      });
    };

    async function buildColumns () {
      const schema = await repo.getSchema();
      const props = schema.properties.data.items.properties.attributes.properties;
      const columns = [];
      for (const propName in props) {
        const prop = props[propName];
        const column: any = {
          title: prop.title || propName,
          dataIndex: propName,
          key: propName
        };
        prop.isFlat = prop.type === 'string';
        if (prop.isFlat) {
          column.sorter = true;
          const columnSearchProps = { ...getColumnSearchProps(propName) };
          Object.assign(column, columnSearchProps);
        }
        columns.push(column);
      }
      columns.push({
        title: 'Actions',
        key: 'actions',
        render: (text: any, record: any) => {
          const boundOnDeleteRecord = onDeleteRecord.bind(null, record);
          return (
            <Space size='middle'>
              <Button danger size='small' onClick={boundOnDeleteRecord}>Delete</Button>
            </Space>
          );
        }
      });
      setColumns(columns);
      setColumnTypes(props);
    }
    buildColumns();
    // eslint-disable-next-line
  }, []);

  useEffect(() => {
    async function fetchTableData () {
      setLoading(true);
      const response = await repo.findAll(tableState);
      const records = response.data?.data === undefined ? [] : response.data?.data;
      const dataSource: any = [];
      if (Array.isArray(records)) {
        records.forEach((record: any) => {
          const row = {
            id: record.id,
            ...record.attributes
          };
          dataSource.push(row);
        });
      }
      // for (const columnName in columnTypes) {
      //     const columnType = columnTypes[columnName];
      //     if (!columnType.isFlat) {
      //         res.data.data.forEach((result: any) => {
      //             result[columnName] = '[complex value]';
      //         });
      //     }
      // }
      let total = 0;

      if (response.data &&
      response.data.meta) {
        total = response.data.meta.pagination.count;
      }
      setData({
        dataSource: dataSource,
        total: total
      });
      setLoading(false);
    }
    // TODO can this skip be avoided somehow -> necessary when columnTypes is not initialized yet
    if (
      columnTypes &&
      Object.keys(columnTypes).length === 0 &&
      Object.getPrototypeOf(columnTypes) === Object.prototype
    ) {
      return;
    }
    fetchTableData();
  }, [tableState, columnTypes, repo]);

  const handleTableChange = (pagination: any, filters: any, sorter: any) => {
    const filterParams: any = {};
    for (const prop in filters) {
      if (filters[prop] && filters[prop].length > 0) {
        filterParams[`filter[${prop}.icontains]`] = filters[prop][0];
      }
    }
    setTableState({
      page: pagination.current,
      pageSize: pagination.pageSize,
      ordering: sorter ? ((sorter.order === 'descend' ? '-' : '') + sorter.field) : '',
      filters: filterParams
    });
  };
  return (
    <Card
      title='Records'
      extra={addRecord ? <Button type='primary' onClick={() => navigate(addRecord)}>Add record</Button> : undefined}
      style={{ width: '100%' }}
    >
      <Table
        dataSource={data.dataSource}
        rowKey={(record: any) => record.id}
        columns={columns}
        loading={loading}
        pagination={{
          current: tableState.page,
          pageSize: tableState.pageSize,
          total: data.total
        }}
        scroll={{ x: true }}
        onChange={handleTableChange}
      />
    </Card>
  );
};

export default ResourceTable;
