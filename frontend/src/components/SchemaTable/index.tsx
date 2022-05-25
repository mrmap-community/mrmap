import { useDefaultWebSocket } from '@/services/WebSockets';
import type { JsonApiPrimaryData } from '@/utils/jsonapi';
import { getQueryParams } from '@/utils/jsonapi';
import { DeleteFilled, EditFilled, InfoCircleOutlined, PlusOutlined } from '@ant-design/icons';
import type { MenuDataItem } from '@ant-design/pro-layout';
import type { ActionType, ColumnsState, ProColumns, ProColumnType, ProTableProps } from '@ant-design/pro-table';
import { default as ProTable } from '@ant-design/pro-table';
import '@ant-design/pro-table/dist/table.css';
import type { TablePaginationConfig } from 'antd';
import { Button, Drawer, Modal, notification, Space, Tooltip } from 'antd';
import type { SortOrder } from 'antd/lib/table/interface';
import type { ParameterObject } from 'openapi-client-axios';
import type { OpenAPIV3 } from 'openapi-types';
import type { ReactElement, ReactNode } from 'react';
import { useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { OpenAPIContext, useOperationMethod } from 'react-openapi-client';
import { generatePath } from 'react-router';
import { FormattedMessage, Link, useIntl, useModel, useParams } from 'umi';
import SchemaForm from '../SchemaForm';
import { buildSearchTransformText, mapOpenApiSchemaToProTableColumn, transformJsonApiPrimaryDataToRow } from './utils';


export interface NestedLookup {
  paramName: string;
  paramValue: string | number;
}

export interface ResourceTypes {
  baseResourceType: string;
  nestedResource?: {
    type: string;
    id: string;
  }
}

export interface SchemaTableProps extends Omit<ProTableProps<any, any>, 'actionRef'> {
  /** Repository that defines the schema and offers CRUD operations */
  resourceTypes: ResourceTypes;
  /** Optional column definitions, automatically augmented and merged with the repository schema */
  columns?: SchemaTableColumnType[];
  additionalActions?: (text: any, record: any) => void;
  defaultActions?: string[];
  /** Path to navigate to for adding records (if omitted, drawer with schema-generated form will open) */
  onAddRecord?: () => void;
  /** Function to invoke for editing records (if omitted, drawer with schema-generated form will open) */
  onEditRecord?: (recordId: number | string) => void;
}

export type SchemaTableColumnType = ProColumnType & {
  /** Optional mapping of query form values to repo filter params */
  toFilterParams?: (value: any) => Record<string, string>;
};


const SchemaTable = ({
  resourceTypes,
  columns = undefined,
  additionalActions = undefined,
  defaultActions = ['edit', 'delete'],
  onAddRecord = undefined,
  onEditRecord = undefined,
  ...passThroughProps
}: SchemaTableProps): ReactElement => {

  const {flatRoutes} = useModel('routes');

  // TODO: check permissions of the user to decide if he can add a resource, if not remove onAddRecord route

  const { id } = useParams<{ id: string }>();

  const _resourceTypes = useMemo(() => {
    if (id){
      const pathname = window.location.pathname;
      const routes = pathname.split('/');
      const indexOfId = routes.indexOf(id);
      
      if (resourceTypes.baseResourceType !== routes[indexOfId+1]) {
        console.log('missmatching baseResourceType passed in by properties. ResourceType founded by route will be owerwrite it.');
      }
      
      return {
        baseResourceType: routes[indexOfId+1],
        nestedResource: {
          id: id,
          type: routes[indexOfId-1]
        }
      };
    } else {
      return resourceTypes;
    }
  }, [id, resourceTypes]);

  const resourceTypesArray = useMemo(() => {
    const list = [_resourceTypes.baseResourceType];
    if (_resourceTypes.nestedResource){
      list.push(_resourceTypes.nestedResource.type)
    }
    return list;
  }, [_resourceTypes]);

  const detailRoute = useMemo<MenuDataItem | undefined>(() => {
    const lookupKey = `${_resourceTypes.baseResourceType}Details`;
    return flatRoutes.find((_route: MenuDataItem) => _route.key === lookupKey);
  }, [_resourceTypes.baseResourceType, flatRoutes]);

  const {lastResourceMessage} = useDefaultWebSocket(resourceTypesArray);

  const intl = useIntl();
  const _defaultActions = useRef(defaultActions);
  const jsonPointer = useRef('reactClient/tables/' + _resourceTypes.baseResourceType);
  const listOperationId: string = 'list' + resourceTypesArray.join('By');

  const { initialState: { settings = undefined } = {}, setInitialState } =
    useModel('@@initialState');

  const [columnsStateMap, setColumnsStateMap] = useState<Record<string, ColumnsState>>(
    settings?.[jsonPointer.current] || {},
  );


  /**
   * @description state variables for right drawer
   */
  const [rightDrawerVisible, setRightDrawerVisible] = useState<boolean>(false);
  const [selectedForEdit, setSelectedForEdit] = useState<string>('');

  /**
   * @description state variables for api calls
   */
  const { api } = useContext(OpenAPIContext);
  const [listResource, { loading: listLoading, error: listError, response: listResponse }] =
    useOperationMethod(listOperationId);
  const [deleteResource, { error: deleteError }] = useOperationMethod('delete' + _resourceTypes.baseResourceType);
  

  /**
   * @description state variables for protable
   */
  const [tableData, setTableData] = useState<JsonApiPrimaryData[]>([]);
  const [paginationConfig, setPaginationConfig] = useState<TablePaginationConfig>();

  const proTableActions = useRef<ActionType>();

  
  const augmentColumns = useCallback((
    properties: any,
    queryParams: any,
    columnHints: ProColumnType[] | undefined,
  ): ProColumns[] => {
    const schemaColumns: any = {};
    for (const propName in properties) {

      schemaColumns[propName] = mapOpenApiSchemaToProTableColumn(
        { dataIndex: propName },
        properties[propName],
        queryParams,
        flatRoutes
      );
      // if there are definitions comes from the inherited component, we overwrite the definitions comes from the schema
      const columnHint = columnHints?.find((hint) => hint.dataIndex === propName);
      if (columnHint) {
        schemaColumns[propName].valueType = 'text';
        for (const [key, value] of Object.entries(columnHint)) {
          schemaColumns[propName][key] = value;
        }
      }
    }
  
    if (queryParams['filter[search]']) {
      schemaColumns.search = {
        dataIndex: 'search',
        title: intl.formatMessage({ id: 'component.schemaTable.searchColumn' }),
        valueType: 'text',
        hideInTable: true,
        hideInSearch: false,
        search: {
          transform: buildSearchTransformText('search'),
        },
      };
    }
    return Object.values(schemaColumns);
  }, [flatRoutes, intl]);


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
    return api.getOperation('add' + _resourceTypes.baseResourceType) ? (
      <Button type="primary" key="primary" onClick={addRowAction()}>
        <Space>
          <PlusOutlined />
          <FormattedMessage id="component.schemaTable.new" />
        </Space>
      </Button>
    ) : null;
  }, [addRowAction, api, _resourceTypes.baseResourceType]);

  const detailsButton = useCallback(
    (row: JsonApiPrimaryData): ReactNode => {

      if (!detailRoute?.path){
        return <></>
      }
      return (
        <Tooltip    
          title={intl.formatMessage({ id: 'component.schemaTable.details' })}
        >
          <Link to={generatePath(detailRoute.path, { id: row.id })}>
            <Button
              size='small'
              style={{ borderColor: 'blue', color: 'blue' }}
              icon={<InfoCircleOutlined />}
            />
          </Link>
        </Tooltip>)
    }, [detailRoute, intl]
  );

  const deleteRowButton = useCallback(
    (row: any): ReactNode => {
      // todo: check if user has permission also
      if (_defaultActions.current.includes('delete') &&
          api.getOperation('delete' + _resourceTypes.baseResourceType)) {
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
            </Tooltip>);
      } else {
        return <></>
      }
    },
    [api, deleteResource, intl, _resourceTypes.baseResourceType],
  );

  const editRowButton = useCallback(
    (row: any): ReactNode => {
      // todo: check if user has permission also
      if (_defaultActions.current.includes('edit') &&
          api.getOperation('update' + _resourceTypes.baseResourceType)) {
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
      } else {
        return <></>
      }
      
    },
    [api, onEditRecord, _resourceTypes.baseResourceType],
  );

  const defaultActionButtons = useCallback(
    (text: any, record: any): ReactNode => {
      return (
        <Space size="small">
          {detailsButton(record)}
          {editRowButton(record)}
          {deleteRowButton(record)}
          {additionalActions ? additionalActions(text, record) : null}
        </Space>
      );
    },
    [additionalActions, deleteRowButton, detailsButton, editRowButton],
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
        settings,
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
  const augmentedColumns = useMemo<ProColumns[]>(() => {
    const queryParams = getQueryParams(api, listOperationId);
    const operation = api.getOperation(listOperationId);
    const responseObject = operation?.responses?.['200'] as OpenAPIV3.ResponseObject;
    const responseSchema = responseObject?.content?.['application/vnd.api+json'].schema as any;
    const schemaColumns: ProColumns[] = []
    if (responseSchema) {
      const attributes = {
        ...responseSchema.properties?.data?.items?.properties?.attributes?.properties,
        ...responseSchema.properties?.data?.items?.properties?.relationships?.properties
      };
      
      schemaColumns.push(...augmentColumns(attributes, queryParams, columns));
      if (!schemaColumns.some((column) => column.key === 'actions')) {
        // TODO: title shall be translated
        schemaColumns.push({
          key: 'operation',
          title: intl.formatMessage({ id: 'component.schemaTable.actionsColumnTitle' }),
          valueType: 'option',
          fixed: 'right',
          render: (text: any, record: any) => {
            return defaultActionButtons(text, record);
          },
        });
      }
    }
    return schemaColumns
  }, [api, augmentColumns, columns, defaultActionButtons, intl, listOperationId]);


  /**
   * @description Handles list response and fills the table with data
   */
  useEffect(() => {
    if (listResponse) {
      const records = listResponse.data.data === undefined ? [] : listResponse.data.data;
      const newData: JsonApiPrimaryData[] = [];
      records.forEach((record: any) => {
        newData.push(transformJsonApiPrimaryDataToRow(record));
      });

      setTableData(newData);
      setPaginationConfig({ total: listResponse.data?.meta?.pagination?.count });
    } else if (!listError && !listLoading) {
      //fetchData();
    }
  }, [listError, listLoading, listResponse]);

  /**
   * @description Builds the query and triggers the async call for the list
   */
  const fetchData = useCallback(
    (params: any, sorter?: Record<string, SortOrder>) => {
      const queryParams = [];
      queryParams.push(
        ...[
          { name: 'page[number]', value: params.current, in: 'query' },
          { name: 'page[size]', value: params.pageSize, in: 'query' },
        ],
      );

      if (_resourceTypes.nestedResource){
        const operation = api.getOperation(listOperationId);
        const firstParam = operation?.parameters?.[0] as ParameterObject;
        if (firstParam){
          queryParams.push({ name: firstParam.name, value: _resourceTypes.nestedResource.id, in: 'path' })

        }
      }

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

      return listResource(queryParams);
    },
    [api, listResource, listOperationId, _resourceTypes.nestedResource],
  );

  /**
   * @description Update handler if there is message received by websocket hook
   */
     useEffect(() => {
      if (tableData?.length > 0 && lastResourceMessage?.payload?.id){
        const existsInCurrentTableView = tableData.findIndex((element: JsonApiPrimaryData) => element.id === lastResourceMessage.payload.id)
        // This is an known element, so we can update it with the received payload
        if (existsInCurrentTableView !== -1 && !lastResourceMessage.type.includes('/delete')){
          const newData = [...tableData];
          newData[existsInCurrentTableView] = transformJsonApiPrimaryDataToRow(lastResourceMessage.payload);
          setTableData(newData);
        } else {
          // this element does not exists in the current table view or was deleted... 
          // for now we simply refresh the table to become the correct data for the current table view
          // This will result in silly reload beahavoir 
          // TODO: think about to handle this better...
          proTableActions.current?.reload();
        }
      }
    // only trigger the hook if lastResourceMessage are changing
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [lastResourceMessage]);

  return (
    <>
      {augmentedColumns.length > 0 && (
        <ProTable
          request={fetchData}
          dataSource={tableData}
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
            augmentedColumns.some((column: SchemaTableColumnType) => {
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
          setRightDrawerVisible(false);
        }}
        destroyOnClose={true}
      >
        <SchemaForm
          resourceType={_resourceTypes.baseResourceType}
          resourceId={selectedForEdit}
          onSuccess={() => {
            setRightDrawerVisible(false);
          }}
        />
      </Drawer>
    </>
  );
};

export default SchemaTable;
