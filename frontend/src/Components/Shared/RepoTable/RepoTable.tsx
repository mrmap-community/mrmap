import { PlusOutlined } from '@ant-design/icons';
import { ActionType, default as ProTable, ProColumnType, ProTableProps } from '@ant-design/pro-table';
import '@ant-design/pro-table/dist/table.css';
import { Button, Modal, notification, Space } from 'antd';
import { SortOrder } from 'antd/lib/table/interface';
import React, { MutableRefObject, ReactElement, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import JsonApiRepo from '../../../Repos/JsonApiRepo';
import { augmentColumnWithJsonSchema } from './TableHelper';



export interface RepoTableProps extends Omit<ProTableProps<any,any>, 'actionRef'> {
    /** Repository that defines the schema and offers CRUD operations */
    repo: JsonApiRepo
    /** Optional column definitions, automatically augmented with the repository schema */
    columns?: RepoTableColumnType[]
    /** Reference to table actions for custom triggering */
    actionRef?: MutableRefObject<RepoActionType> | ((actions: RepoActionType) => void)
    /** Path to navigate to for adding records (if omitted, no 'New' button will be available) */
    onAddRecord?: string
    /** Function to invoke for editing records (if omitted, no 'Edit' button will be available) */
    onEditRecord?: (recordId: number | string) => void
}

export type RepoTableColumnType = ProColumnType & {
  /** Optional mapping of query form values to repo filter params */
  toFilterParams?: (value: any) => { [key: string]: string; }
}

// extends ActionType from Pro Table
// https://procomponents.ant.design/en-US/components/table/?current=1&pageSize=5#protable
export type RepoActionType = ActionType & {
  deleteRecord: (row:any) => void
}

function augmentColumns (resourceSchema: any, queryParams: any,
  columnHints: ProColumnType[] | undefined): ProColumnType[] {
  const props = resourceSchema.properties?.data?.items?.properties?.attributes?.properties;
  const columns:any = {};
  // phase 1: add a column for every column hint, merge with schema property definition (if available)
  if (columnHints) {
    columnHints.forEach((columnHint) => {
      const columnName = columnHint.dataIndex as string;
      const schema = props[columnName];
      if (schema) {
        columns[columnName] = augmentColumnWithJsonSchema(columnHint, schema, queryParams);
      } else {
        columns[columnName] = columnHint;
      }
    });
  }
  // phase 2: add a column for every schema property that does not have a corresponding column hint
  for (const propName in props) {
    if (propName in columns) {
      continue;
    }
    const prop = props[propName];
    const columnHint = {
      dataIndex: propName
    };
    columns[propName] = augmentColumnWithJsonSchema(columnHint, prop, queryParams);
  }
  return Object.values(columns);
}

const RepoTable = ({
  repo,
  columns = undefined,
  actionRef = undefined,
  onAddRecord = undefined,
  onEditRecord = undefined,
  ...passThroughProps
}: RepoTableProps): ReactElement => {
  const navigate = useNavigate();
  const [augmentedColumns, setAugmentedColumns] = useState<any>([]);

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

  // augment / build columns from schema (and add delete action)
  useEffect(() => {
    let isMounted = true;
    async function buildColumns () {
      const resourceSchema = await repo.getResourceSchema();
      const queryParams = await repo.getQueryParams();
      const _augmentedColumns = augmentColumns(resourceSchema, queryParams, columns);
      if (!_augmentedColumns.some(column => column.key === 'actions')) {
        _augmentedColumns.push({
          key: 'actions',
          title: 'Aktionen',
          valueType: 'option',
          render: (text: any, record: any) => {
            return (
              <>
                <Space size='middle'>
                  {onEditRecord && (
                    <Button
                      size='small'
                      onClick={() => onEditRecord(record.id)}
                    >
                    Bearbeiten
                    </Button>
                  )}
                  <Button
                    danger
                    size='small'
                    onClick={() => actions.current?.deleteRecord(record)}
                  >
                  Löschen
                  </Button>
                </Space>
              </>
            );
          }
        });
      }
      isMounted && setAugmentedColumns(_augmentedColumns);
    }
    buildColumns();
    return () => { isMounted = false; }; // componentWillUnmount handler
  }, [columns, onEditRecord, repo]);

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
      if (prop !== 'current' && prop !== 'pageSize' && params[prop]) {
        filters[prop] = params[prop];
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
          layers: [],
          ...record.attributes
        };
        if(record.relationships?.selfPointingLayers?.data.length > 0){
          const layerIds = record.relationships.selfPointingLayers.data.map((d:any) => d.id);
          row.layers = layerIds;
        }
        if(record.relationships.allowedOperations?.meta?.count){
          row.allowedOperations = record.relationships.allowedOperations.meta.count;
        }        
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
    <>{ augmentedColumns.length > 0 && (
      <ProTable
        request={fetchData}
        columns={augmentedColumns}
        scroll={{ x: true }}
        headerTitle={repo.displayName}
        actionRef={setActions}
        dateFormatter={false}
        toolBarRender={onAddRecord
          ? () => [
            <Button
              type='primary'
              key='primary'
              onClick={() => {
                navigate(onAddRecord as string);
              }}
            >
              <PlusOutlined />Neu
            </Button>
          ]
          : () => []}
        search={ augmentedColumns.some((column: RepoTableColumnType) => {
          return column.search && column.search.transform;
        })
          ? {
            layout: 'vertical'
          }
          : false}
        {...passThroughProps}
      />)}</>
  );
};

export default RepoTable;
