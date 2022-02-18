import { DeleteFilled, EditFilled, PlusOutlined } from '@ant-design/icons';
import { ActionType, default as ProTable, ProColumnType, ProTableProps } from '@ant-design/pro-table';
import '@ant-design/pro-table/dist/table.css';
import { Button, Modal, notification, Space, TablePaginationConfig, Tooltip } from 'antd';
import { SortOrder } from 'antd/lib/table/interface';
import { OpenAPIV3 } from 'openapi-types';
import React, { MutableRefObject, ReactElement, useEffect, useRef, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useNavigate } from 'react-router';
import { getQueryParams } from '../../../Utils/JsonApiUtils';
import { augmentColumnWithJsonSchema } from './TableHelper';

export interface RepoTableProps extends Omit<ProTableProps<any,any>, 'actionRef'> {
    /** Repository that defines the schema and offers CRUD operations */
    resourceType: string
    /** Optional column definitions, automatically augmented with the repository schema */
    columns?: RepoTableColumnType[]
    additionalActions?: (text: any, record:any) => void
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
  editRecord: (row: any) => void
}

function augmentColumns (
  resourceSchema: any, 
  queryParams: any,
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
  resourceType,
  columns = undefined,
  additionalActions = undefined,
  actionRef = undefined,
  onAddRecord = undefined,
  onEditRecord = undefined,
  ...passThroughProps
}: RepoTableProps): ReactElement => {

  // TODO: check permissions of the user to decide if he can add a resource, if not remove onAddRecord route


  const navigate = useNavigate();
  const [augmentedColumns, setAugmentedColumns] = useState<any>([]);
  const [header, setHeader]= useState<string>(resourceType);
  // eslint-disable-next-line max-len
  const [listResource, { loading: listLoading, error: listError, response: listResponse, api: listApi }] = useOperationMethod('list'+resourceType);
  const [deleteResource, { error: deleteError, api: deleteApi }] = useOperationMethod('delete'+resourceType);
  const [editResource, { error: editError, api: editApi }] = useOperationMethod('update'+resourceType);


  const tableDataSourceInit = {
    data: [],
    success: true,
    total: 0
  };
  const [tableDataSource, setTableDataSource] = useState<any>(tableDataSourceInit);
  const [paginationConfig, setPaginationConfig] = useState<TablePaginationConfig>();

  const actions = useRef<RepoActionType>();
  const setActions = (proTableActions: ActionType) => {
    actions.current = {
      ...proTableActions,
      deleteRecord: (row:any) => {
        const modal = Modal.confirm({
          title: 'Delete record',
          content: `Do you want to delete the record with id ${row.id}?`,
          onOk: () => {
            modal.update(prevConfig => ({
              ...prevConfig,
              confirmLoading: true
            }));

            deleteResource(row.id);
            proTableActions.reload();
          }
        });
      },
      editRecord: (row:any) => {
        console.log(row);
      }
    };
    if (typeof actionRef === 'function') {
      actionRef(actions.current);
    } else if (actionRef) {
      actionRef.current = actions.current;
    }
  };

  useEffect(() => {
    if (deleteError) {
      notification.error({ message: 'Something went wrong. Can\'t delete resource.' });
    }
  }, [deleteError]);

  // augment / build columns from schema (and add delete action)
  useEffect(() => {
    let isMounted = true;
  
    const queryParams = getQueryParams(listApi, 'list'+resourceType);
    const operation = listApi.getOperation('list'+resourceType);

    const responseObject = operation?.responses?.['200'] as OpenAPIV3.ResponseObject;
    const responseSchema = responseObject?.content?.['application/vnd.api+json'].schema as any;
    if (responseSchema) {
      if (responseSchema.properties?.data.items.title){
        setHeader(responseSchema.properties?.data.items.title);
      }
      
      const _augmentedColumns = augmentColumns(responseSchema, queryParams, columns);
      if (!_augmentedColumns.some(column => column.key === 'actions')) {
        
        _augmentedColumns.push({
          key: 'actions',
          title: 'Aktionen',
          valueType: 'option',

          render: (text: any, record: any) => {
            return (
              <>
                <Space size='small'>
                  { // todo: check if user has permission also
                    editApi.getOperation('update'+resourceType) ? 
                      <Tooltip 
                        title={ 'Edit' }>
                        <Button
                          size='small'
                          icon={<EditFilled/>}
                          style={{ borderColor: 'gold', color: 'gold' }}
                          onClick={() => actions.current?.editRecord(record)}
                        />
                      </Tooltip>
                      : null}
                  { // todo: check if user has permission also
                    deleteApi.getOperation('delete'+resourceType) ?
                      <Tooltip 
                        title={ 'Delete' }>
                        <Button
                          style={{ borderColor: 'red', color: 'red' }}
                          type='default'
                          icon={<DeleteFilled/>}
                          size='small'
                          onClick={() => actions.current?.deleteRecord(record)}
                        />
                      </Tooltip>
                      : null}
                  {additionalActions ? additionalActions(text, record) : null}
                </Space>
              </>
            );
          }
        });
      }
      isMounted && setAugmentedColumns(_augmentedColumns);
    }
    
    return () => { isMounted = false; }; // componentWillUnmount handler
  },[additionalActions, columns, deleteApi, editApi, listApi, resourceType]);

  useEffect(() => {
    if (listResponse) {
      const records = listResponse.data.data === undefined ? [] : listResponse.data.data;
      const data: any = [];
      if (Array.isArray(records)) {
        records.forEach((record: any) => {
          const row = {
            key: record.id,
            id: record.id,
            layers: [],
            ...record.attributes
          };
          // TODO: remove this from this component... this is layer specific stuff
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
        //current: listResponse.data.meta.pagination.page,
        data: data,
        success: listError,
        total: listResponse.data.meta.pagination.count
      };
      setTableDataSource(dataSource);
      setPaginationConfig({ total: dataSource.total });
    }
    
  }, [listError, listResponse]);

  // fetches data in format expected by antd ProTable component
  function fetchData (params: any, sorter?: Record<string, SortOrder>) {
    const queryParams = [
      { name: 'page[number]', value: params.current, in: 'query' },
      { name: 'page[size]', value: params.pageSize, in: 'query' },
    ];
    
    let ordering = '';
    if (sorter) {
      for (const prop in sorter) {
        // TODO handle multi property ordering
        ordering = (sorter[prop] === 'descend' ? '-' : '') + prop;
      }
    }
    if (ordering !== '') {
      queryParams.push({ name: 'sort', value: ordering, in: 'query' });
    }
    for (const prop in params) {
      // 'current' and 'pageSize' are reserved names in antd ProTable (and cannot be used for filtering)
      if (prop !== 'current' && prop !== 'pageSize' && params[prop]) {
        queryParams.push({ name: prop, value: params[prop], in: 'query' });
      }
    }

    listResource(queryParams);
    return tableDataSource;
  }

  return (
    <>{ augmentedColumns.length > 0 && (
      <ProTable
        request={fetchData}
        dataSource={tableDataSource.data}
        loading={listLoading}
        columns={augmentedColumns}
        scroll={{ x: true }}
        headerTitle={header}
        actionRef={setActions}
        dateFormatter={false}
        pagination={paginationConfig}
        toolBarRender={onAddRecord
          ? () => [
            <Button
              type='primary'
              key='primary'
              onClick={() => {
                navigate(onAddRecord);
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
