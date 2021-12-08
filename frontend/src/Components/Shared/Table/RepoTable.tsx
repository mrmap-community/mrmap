import '@ant-design/pro-table/dist/table.css';

import { PlusOutlined } from '@ant-design/icons';
import ProTable, { ActionType, ProColumnType } from '@ant-design/pro-table';
import { Button, Card, Modal, notification, Space } from 'antd';
import { SortOrder } from 'antd/lib/table/interface';
import React, { MutableRefObject, ReactElement, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';

import JsonApiRepo from '../../../Repos/JsonApiRepo';
import { augmentColumnWithJsonSchema } from './TableHelper';

interface RepoTableProps {
    repo: JsonApiRepo
    actionRef?: MutableRefObject<RepoActionType> | ((actions: RepoActionType) => void)
    addRecord?: string
    editRecord?: boolean,
    onEditRecord?: (recordId: number | string) => void,
    columnHints?: ProColumnType[],
}

export type RepoActionType = ActionType & {
  deleteRecord: (row:any) => void
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
  }
  return Object.values(columns);
}

export const RepoTable = ({
  repo,
  actionRef = undefined,
  addRecord,
  editRecord = false,
  onEditRecord = () => undefined,
  columnHints = undefined
}: RepoTableProps): ReactElement => {
  const navigate = useNavigate();
  const [columns, setColumns] = useState<any>([]);

  const actions = useRef<RepoActionType>();
  const setActions = (proTableActions: ActionType) => {
    actions.current = {
      ...proTableActions,
      deleteRecord: (row:any) => {
        async function deleteFromRepo () {
          await repo.delete(row.id);
          notification.success({
            message: 'Record deleted',
            description: `Record with id ${row.id} has been deleted succesfully`
          });
        }
        const modal = Modal.confirm({
          title: 'Delete record',
          content: `Do you want to delete the record with id ${row.id}?`,
          onOk: () => {
            modal.update(prevConfig => ({
              ...prevConfig,
              confirmLoading: true
            }));
            deleteFromRepo();
            proTableActions.reload();
          }
        });
      }
    };
    if (typeof actionRef === 'function') {
      actionRef(actions.current);
    } else if (actionRef) {
      actionRef.current = actions.current;
    }
  };

  // build columns from schema (and add delete action)
  useEffect(() => {
    async function buildColumns () {
      const schema = await repo.getSchema();
      const columns = deriveColumns(schema, columnHints);
      if (!columns.some(column => column.key === 'actions')) {
        columns.push({
          title: 'Actions',
          key: 'actions',
          valueType: 'option',
          render: (text: any, record: any) => {
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
                  onClick={() => actions.current?.deleteRecord(record)}
                >
                  Delete
                </Button>
              </Space>
            </>
            );
          }
        });
      }
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
        actionRef={setActions}
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
