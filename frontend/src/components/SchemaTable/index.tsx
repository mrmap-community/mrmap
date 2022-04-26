import { getQueryParams } from '@/utils/jsonapi';
import { DeleteFilled, EditFilled, PlusOutlined } from '@ant-design/icons';
import type { ActionType, ColumnsState, ProColumnType, ProTableProps } from '@ant-design/pro-table';
import { default as ProTable } from '@ant-design/pro-table';
import '@ant-design/pro-table/dist/table.css';
import type { TablePaginationConfig } from 'antd';
import { Button, Drawer, Modal, notification, Space, Tooltip } from 'antd';
import type { SortOrder } from 'antd/lib/table/interface';
import type { ParamsArray } from 'openapi-client-axios';
import type { OpenAPIV3 } from 'openapi-types';
import type { ReactElement, ReactNode } from 'react';
import { useCallback, useContext, useEffect, useRef, useState } from 'react';
import { OpenAPIContext, useOperationMethod } from 'react-openapi-client';
import { FormattedMessage, useIntl, useModel } from 'umi';
import SchemaForm from '../SchemaForm';
import { buildSearchTransformText, mapOpenApiSchemaToProTableColumn } from './utils';

export interface NestedLookup {
  paramName: string;
  paramValue: string | number;
}

export interface RepoTableProps extends Omit<ProTableProps<any, any>, 'actionRef'> {
  /** Repository that defines the schema and offers CRUD operations */
  resourceTypes: string[];
  nestedLookups?: ParamsArray;
  /** Optional column definitions, automatically augmented and merged with the repository schema */
  columns?: RepoTableColumnType[];
  additionalActions?: (text: any, record: any) => void;
  defaultActions?: string[];
  /** Path to navigate to for adding records (if omitted, drawer with schema-generated form will open) */
  onAddRecord?: () => void;
  /** Function to invoke for editing records (if omitted, drawer with schema-generated form will open) */
  onEditRecord?: (recordId: number | string) => void;
}

export type RepoTableColumnType = ProColumnType & {
  /** Optional mapping of query form values to repo filter params */
  toFilterParams?: (value: any) => Record<string, string>;
};

function augmentColumns(
  resourceSchema: any,
  queryParams: any,
  columnHints: ProColumnType[] | undefined,
): ProColumnType[] {
  const props = resourceSchema.properties?.data?.items?.properties?.attributes?.properties;
  const columns: any = {};
  for (const propName in props) {
    columns[propName] = mapOpenApiSchemaToProTableColumn(
      { dataIndex: propName },
      props[propName],
      queryParams,
    );
    const columnHint = columnHints?.find((hint) => hint.dataIndex === propName);
    if (columnHint) {
      columns[propName].valueType = 'text';
      for (const [key, value] of Object.entries(columnHint)) {
        columns[propName][key] = value;
      }
    }
  }

  if (queryParams['filter[search]']) {
    columns.search = {
      dataIndex: 'search',
      title: 'Suchbegriffe',
      valueType: 'text',
      hideInTable: true,
      hideInSearch: false,
      search: {
        transform: buildSearchTransformText('search'),
      },
    };
  }
  return Object.values(columns);
}

const SchemaTable = ({
  resourceTypes,
  nestedLookups = [],
  columns = undefined,
  additionalActions = undefined,
  defaultActions = ['edit', 'delete'],
  onAddRecord = undefined,
  onEditRecord = undefined,
  ...passThroughProps
}: RepoTableProps): ReactElement => {
  const intl = useIntl();
  const _defaultActions = useRef(defaultActions);
  const jsonPointer = useRef('reactClient/tables/' + resourceTypes[0]);
  const nestedResourceListLookup: string = 'list' + resourceTypes.join('By');
  
  const { initialState: { settings = undefined } = {}, setInitialState } = useModel('@@initialState');

  const [columnsStateMap, setColumnsStateMap] = useState<Record<string, ColumnsState>>(
    settings?.[jsonPointer.current] || {},
  );

  const [augmentedColumns, setAugmentedColumns] = useState<any>([]);

  // TODO: check permissions of the user to decide if he can add a resource, if not remove onAddRecord route
  const [rightDrawerVisible, setRightDrawerVisible] = useState<boolean>(false);
  const [selectedForEdit, setSelectedForEdit] = useState<string>('');
  const closeRightDrawer = useCallback(() => {
    setRightDrawerVisible(false);
    setSelectedForEdit('');
  }, []);
  const { api } = useContext(OpenAPIContext);
  const [listResource, { loading: listLoading, error: listError, response: listResponse }] =
    useOperationMethod(nestedResourceListLookup);
  const [deleteResource, { error: deleteError }] = useOperationMethod('delete' + resourceTypes[0]);

  const [tableDataSource, setTableDataSource] = useState<any>({
    data: [],
    success: true,
    total: 0,
  });
  const [paginationConfig, setPaginationConfig] = useState<TablePaginationConfig>();

  const proTableActions = useRef<ActionType>();

  const addRowAction = useCallback(() => {
    return !onAddRecord
      ? () => {
          setRightDrawerVisible(true);
        }
      : () => {
          onAddRecord();
        };
  }, [onAddRecord]);

  const addRowButton = useCallback((): ReactNode => {
    return api.getOperation('add' + resourceTypes[0]) ? (
      <Button type="primary" key="primary" onClick={addRowAction()}>
        <Space>
          <PlusOutlined />
          <FormattedMessage id="component.schemaTable.new" />
        </Space>
      </Button>
    ) : null;
  }, [addRowAction, api, resourceTypes]);

  const deleteRowButton = useCallback(
    (row: any): ReactNode => {
      return (
        <Tooltip title={'Delete'}>
          <Button
            style={{ borderColor: 'red', color: 'red' }}
            type="default"
            icon={<DeleteFilled />}
            size="small"
            onClick={() => {
              const modal = Modal.confirm({
                title: intl.formatMessage({ id: 'component.schemaTable.deleteRowTitle' }),
                content: intl.formatMessage(
                  { id: 'component.schemaTable.deleteRowText' },
                  { row: row.id },
                ),
                onOk: () => {
                  modal.update((prevConfig) => ({
                    ...prevConfig,
                    confirmLoading: true,
                  }));
                  deleteResource(row.id);
                  proTableActions.current?.reload();
                },
              });
            }}
          />
        </Tooltip>
      );
    },
    [deleteResource, intl],
  );

  const editRowButton = useCallback(
    (row: any): ReactNode => {
      return (
        <Tooltip title={'Edit'}>
          <Button
            size="small"
            icon={<EditFilled />}
            style={{ borderColor: 'gold', color: 'gold' }}
            onClick={() => {
              if (onEditRecord) {
                onEditRecord(row.id);
              } else {
                setSelectedForEdit(row.id);
                setRightDrawerVisible(true);
              }
            }}
          />
        </Tooltip>
      );
    },
    [onEditRecord],
  );

  const defaultActionButtons = useCallback(
    (text: any, record: any): ReactNode => {
      return (
        <Space size="small">
          {
            // todo: check if user has permission also
            _defaultActions.current.includes('edit') &&
            api.getOperation('update' + resourceTypes[0])
              ? editRowButton(record)
              : null
          }
          {
            // todo: check if user has permission also
            _defaultActions.current.includes('delete') &&
            api.getOperation('delete' + resourceTypes[0])
              ? deleteRowButton(record)
              : null
          }
          {additionalActions ? additionalActions(text, record) : null}
        </Space>
      );
    },
    [additionalActions, api, deleteRowButton, editRowButton, resourceTypes],
  );


  /**
   * @description Updates columeStateMap on user settings
   */
  useEffect(() => {
    if (columnsStateMap) {
      const newSettings = settings || {};
      newSettings[jsonPointer.current] = columnsStateMap;
      
      setInitialState((s: any) => ({
        ...s,
        settings
      }));
    }
  }, [columnsStateMap, setInitialState, settings]);

  /**
   * @description Handles errors on row delete
   */
  useEffect(() => {
    if (deleteError) {
      notification.error({ message: "Something went wrong. Can't delete resource." });
    }
  }, [deleteError]);

  // augment / build columns from schema (and add delete action)
  useEffect(() => {
    const queryParams = getQueryParams(api, nestedResourceListLookup);
    const operation = api.getOperation(nestedResourceListLookup);
    const responseObject = operation?.responses?.['200'] as OpenAPIV3.ResponseObject;
    const responseSchema = responseObject?.content?.['application/vnd.api+json'].schema as any;
    if (responseSchema) {
      const _augmentedColumns = augmentColumns(responseSchema, queryParams, columns);
      if (!_augmentedColumns.some((column) => column.key === 'actions')) {
        _augmentedColumns.push({
          key: 'operation',
          title: 'Aktionen',
          valueType: 'option',
          fixed: 'right',
          render: (text: any, record: any) => {
            return defaultActionButtons(text, record);
          },
        });
      }
      setAugmentedColumns(_augmentedColumns);
    }
  }, [additionalActions, columns, api, nestedResourceListLookup, defaultActionButtons]);

  /**
   * @description Handles list response and fills the table with data
   */
  useEffect(() => {
    if (listResponse) {
      const records = listResponse.data.data === undefined ? [] : listResponse.data.data;
      const data: any = [];
      records.forEach((record: any) => {
        const row = {
          key: record.id,
          id: record.id,
          ...record.attributes,
          relationships: { ...record.relationships },
        };
        data.push(row);
      });

      const dataSource = {
        data: data,
        success: listError,
        total: listResponse.data.meta.pagination.count,
      };
      setTableDataSource(dataSource);
      setPaginationConfig({ total: dataSource.total });
    } else if (!listError && !listLoading) {
      //fetchData();
    }
  }, [listError, listLoading, listResponse]);

  /**
   * @description Builds the query and triggers the async call for the list
   */
  const fetchData = useCallback(
    (params: any, sorter?: Record<string, SortOrder>) => {
      const queryParams = [...nestedLookups];
      queryParams.push(
        ...[
          { name: 'page[number]', value: params.current, in: 'query' },
          { name: 'page[size]', value: params.pageSize, in: 'query' },
        ],
      );

      let ordering = '';
      for (const prop in sorter) {
        // TODO handle multi property ordering
        ordering = (sorter[prop] === 'descend' ? '-' : '') + prop;
      }
      if (ordering) {
        queryParams.push({ name: 'sort', value: ordering, in: 'query' });
      }

      // 'current' and 'pageSize' are reserved names in antd ProTable (and cannot be used for filtering)
      delete params.current;
      delete params.pageSize;

      for (const prop in params) {
        queryParams.push({ name: prop, value: params[prop], in: 'query' });
      }

      listResource(queryParams);
      return tableDataSource;
    },
    [listResource, nestedLookups, tableDataSource],
  );

  return (
    <>
      {augmentedColumns.length > 0 && (
        <ProTable
          request={fetchData}
          dataSource={tableDataSource.data}
          loading={listLoading}
          columns={augmentedColumns}
          scroll={{ x: true }}
          actionRef={proTableActions}
          dateFormatter={false}
          pagination={paginationConfig}
          toolBarRender={() => [addRowButton()]}
          columnsState={
            passThroughProps.columnsState
              ? passThroughProps.columnsState
              : {
                  value: columnsStateMap,
                  onChange: setColumnsStateMap,
                }
          }
          search={
            augmentedColumns.some((column: RepoTableColumnType) => {
              return column.search && column.search.transform;
            })
              ? {
                  layout: 'vertical',
                }
              : false
          }
          {...passThroughProps}
        />
      )}
      <Drawer
        title={
          selectedForEdit
            ? intl.formatMessage({ id: 'component.schemaTable.edit' }, { title: selectedForEdit })
            : intl.formatMessage({ id: 'component.schemaTable.create' })
        }
        placement="right"
        visible={rightDrawerVisible}
        onClose={() => {
          closeRightDrawer();
        }}
      >
        <SchemaForm
          resourceType={resourceTypes[0]}
          resourceId={selectedForEdit}
          onSuccess={() => {
            closeRightDrawer();
          }}
        />
      </Drawer>
    </>
  );
};

export default SchemaTable;
