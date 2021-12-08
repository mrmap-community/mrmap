import '@ant-design/pro-table/dist/table.css';

import { PlusOutlined } from '@ant-design/icons';
import ProTable, { ProColumnType } from '@ant-design/pro-table';
import { Button, Card, Modal, notification, Space } from 'antd';
import { SortOrder } from 'antd/lib/table/interface';
import React, { ReactElement, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';

import JsonApiRepo from '../../../Repos/JsonApiRepo';
import { augmentColumnWithJsonSchema } from './TableHelper';

interface RepoTableProps {
    repo: JsonApiRepo
    addRecord?: string
    editRecord?: boolean,
    onEditRecord?: (recordId: number | string) => void,
    columnHints?: ProColumnType[];
}

function deriveColumns (resourceSchema: any, columnHints: ProColumnType[] | undefined): ProColumnType[] {
  const props = resourceSchema.properties.data.items.properties.attributes.properties;
  const columns:any = {};
  if (columnHints) {
    columnHints.forEach((columnHint) => {
      const columnName = columnHint.dataIndex as string;
      const schema = props[columnName];
      columns[columnName] = augmentColumnWithJsonSchema(columnHint, schema);
    });
  }
  for (const propName in props) {
    if (propName in columns) {
      continue;
    }
    const prop = props[propName];
    const columnHint = {
      dataIndex: propName
    };
    columns[propName] = augmentColumnWithJsonSchema(columnHint, prop);
    // const column: any = {
    //   title: prop.title || propName,
    //   dataIndex: propName,
    //   key: propName,
    //   valueType: undefined
    // };
    // prop.isFlat = prop.type === 'string';
    // if (prop.isFlat) {
    //   column.sorter = true;
    // }
    // columns.push(column);
  }
  return Object.values(columns);
}

export const RepoTable = ({
  repo,
  addRecord,
  editRecord = false,
  onEditRecord = () => undefined,
  columnHints = undefined
}: RepoTableProps): ReactElement => {
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
      console.log('schema', schema);
      const columns = deriveColumns(schema, columnHints);
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

export default RepoTable;
