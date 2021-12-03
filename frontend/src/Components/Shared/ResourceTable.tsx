import '@ant-design/pro-table/dist/table.css';

import { PlusOutlined } from '@ant-design/icons';
import ProTable, { ProColumnType } from '@ant-design/pro-table';
import { Button, Card, Modal, notification, Space } from 'antd';
import { SortOrder } from 'antd/lib/table/interface';
import React, { ReactElement, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';

import JsonApiRepo from '../../Repos/JsonApiRepo';

interface ResourceTableProps {
    repo: JsonApiRepo
    addRecord?: string
    editRecord?: boolean,
    onEditRecord?: (recordId: number | string) => void;
}

function deriveColumns (resourceSchema: any): ProColumnType[] {
  const props = resourceSchema.properties.data.items.properties.attributes.properties;
  const columns = [];
  for (const propName in props) {
    const prop = props[propName];
    // https://procomponents.ant.design/components/schema#valuetype
    // let valueType = 'text';
    // if (prop.type === 'string') {
    //   if (prop.format === 'date-time') {
    //     // valueType = 'dateTime';
    //     valueType = 'dateTimeRange';
    //   }
    // } else if (prop.type === 'integer') {
    //   valueType = 'digit';
    // }
    const column: any = {
      title: prop.title || propName,
      dataIndex: propName,
      key: propName,
      valueType: undefined
    };
    prop.isFlat = prop.type === 'string';
    if (prop.isFlat) {
      column.sorter = true;
    }
    columns.push(column);
  }
  return columns;
}

export const ResourceTable = ({
  repo,
  addRecord,
  editRecord = false,
  onEditRecord = () => undefined
}: ResourceTableProps): ReactElement => {
  const navigate = useNavigate();
  const actionRef = useRef();
  const [columns, setColumns] = useState<any>([]);

  // build columns from schema (and add delete action)
  useEffect(() => {
    const onDeleteRecord = (record: any) => {
      async function deleteRecord () {
        await repo.delete(record.id);
        notification.success({
          message: 'Record deleted',
          description: `Record with id ${record.id} has been deleted succesfully`
        });
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
          if (actionRef.current) {
            (actionRef.current as any).reload();
          }
        }
      });
    };

    async function buildColumns () {
      const schema = await repo.getSchema();
      const columns = deriveColumns(schema);
      columns.push({
        title: 'Actions',
        key: 'actions',
        valueType: 'option',
        render: (text: any, record: any) => {
          const boundOnDeleteRecord = onDeleteRecord.bind(null, record);
          return (
            <>
              <Space size='middle'>
              {editRecord && (
                  <Button
                    size='small'
                    onClick={() => onEditRecord(record.id)}
                  >
                    Edit
                  </Button>
              )}
                <Button
                  danger
                  size='small'
                  onClick={boundOnDeleteRecord}
                >
                  Delete
                </Button>

              </Space>
            </>
          );
        }
      });
      setColumns(columns);
    }
    buildColumns();
  }, []);

  // fetches data in format expected by antd ProTable component
  async function fetchData (params: any, sorter?: Record<string, SortOrder>): Promise<any> {
    let ordering = '';
    if (sorter) {
      for (const prop in sorter) {
        // TODO handle multi property ordering
        ordering = (sorter[prop] === 'descend' ? '-' : '') + prop;
      }
    }
    const filters:any = {};
    for (const prop in params) {
      // 'current' and 'pageSize' are reserved names in antd ProTable (and cannot be used for filtering)
      if (prop !== 'current' && prop !== 'pageSize') {
        // TODO respect backend filtering capabilities
        filters[`filter[${prop}.icontains]`] = params[prop];
      }
    }
    const queryParams = {
      page: params.current,
      pageSize: params.pageSize,
      ordering: ordering,
      filters: filters
    };
    const response = await repo.findAll(queryParams);
    const records = response.data?.data === undefined ? [] : response.data?.data;
    const data: any = [];
    if (Array.isArray(records)) {
      records.forEach((record: any) => {
        const row = {
          key: record.id,
          id: record.id,
          ...record.attributes
        };
        data.push(row);
      });
    }
    const dataSource = {
      current: response.data?.meta.pagination.page,
      data: data,
      pageSize: params.pageSize,
      success: true,
      total: response.data?.meta.pagination.count
    };
    return dataSource;
  }

  return (
  <Card
    title='WebMapServices'
    style={{ width: '100%' }}
  >
    { columns.length > 0 && (<ProTable
        request={fetchData}
        columns={columns}
        scroll={{ x: true }}
        headerTitle={'Records'}
        actionRef={actionRef}
        // search={false}
        // toolBarRender={false}
        toolBarRender={() => [
          <Button
            type='primary'
            key='primary'
            onClick={() => {
              navigate(addRecord as string);
            }}
          >
            <PlusOutlined />New
          </Button>
        ]}
    />)}

  </Card>
  );
};

export default ResourceTable;
