import { useMemo, type ReactElement } from 'react';
import {
  Admin,
  CustomRoutes,
  defaultTheme,
  Loading,
  localStorageStore,
  Resource,
  type RaThemeOptions
} from 'react-admin';
import { Route } from 'react-router-dom';

import { type Operation as AxiosOperation, type OpenAPIV3 } from 'openapi-client-axios';

import { useHttpClientContext } from '../context/HttpClientContext';
import CreateGuesser from '../jsonapi/components/CreateGuesser';
import EditGuesser from '../jsonapi/components/EditGuesser';
import ListGuesser from '../jsonapi/components/ListGuesser';
import { getResourceSchema } from '../jsonapi/openapi/parser';
import authProvider from '../providers/authProvider';
import jsonApiDataProvider from '../providers/dataProvider';
import Dashboard from './Dashboard/Dashboard';
import MyLayout from './Layout/Layout';
import MapViewer from './MapViewer/MapViewer';
import PortalSearch from './PortalSearch/PortalSearch';
import defaultRecordRepresentation from './Resource/defaultRecordRepresentation';
import RESOURCES from './Resource/Definition';

const STORE_VERSION = '1'


const MrMapFrontend = (): ReactElement => {
  const lightTheme = defaultTheme
  const customTheme: RaThemeOptions = { ...defaultTheme, transitions: {} }

  const darkTheme: RaThemeOptions = { ...defaultTheme, palette: { mode: 'dark' } }

  const { api, authToken, setAuthToken, getWebSocket, readyState} = useHttpClientContext()

  const dataProvider = useMemo(() => {
    const websocket = getWebSocket()
    return api && jsonApiDataProvider({
      httpClient: api, 
      ...(websocket !== null && { realtimeBus: websocket }),
    })
  }, [api, readyState])
  
  const resourceDefinitions = useMemo(() => {
    return RESOURCES.map((resource)=> {
      const showOperationName = `retreive_${resource.name}`
      const createOperationName = `create_${resource.name}`
      const editOperationName = `partial_update_${resource.name}`
      const listOperationName =`list_${resource.name}`

      const createOperation = api?.getOperation(createOperationName)
      const editOperation = api?.getOperation(editOperationName)
      const listOperation = api?.getOperation(listOperationName)

      const related_list_operations = api?.getOperations().filter((operation) => operation.operationId?.includes(`_of_${resource.name}`)) as AxiosOperation[]
      const related_list_resources = related_list_operations?.map((schema) => {
        const resourceSchema = getResourceSchema(schema)

        const properties = resourceSchema?.properties?.data as OpenAPIV3.ArraySchemaObject
        const items = properties.items as OpenAPIV3.SchemaObject
        const jsonApiTypeProperty = items?.properties?.type as OpenAPIV3.NonArraySchemaObject
        const jsonApiTypeReferences = jsonApiTypeProperty?.allOf as OpenAPIV3.SchemaObject[]
        return jsonApiTypeReferences?.[0]?.enum?.[0] as string
      }) ?? []

      return {
        ...(resource.create || createOperation && {create: CreateGuesser, hasCreate: true}),
        ...(resource.list || listOperation && {list: ListGuesser, hasList: true}),
        ...(resource.edit || editOperation && {edit: EditGuesser, hasEdit: true}),
        // TODO: merge children and related_list_operations paths
        ...(resource.children || related_list_operations && { 
          children: related_list_resources.map((relatedResource) => <Route key={`nested-${relatedResource}-of-${resource.name}`} path={`:id/${relatedResource}`} element={<ListGuesser resource={relatedResource} relatedResource={resource.name}> </ListGuesser>}></Route>)
        }) as ReactElement[],
        ...(resource.recordRepresentation ? {recordRepresentation: resource.recordRepresentation}: {recordRepresentation: defaultRecordRepresentation}),
        ...({options: {...resource.options, 
              showOperationName: showOperationName,
              createOperationName: createOperationName,
              editOperationName: editOperationName,
              listOperationName: listOperationName
            }}),
        ...resource,
        
      }
    })
  }, [api])

  if (dataProvider === undefined) {
    return (
      <Loading loadingPrimary="Initialize...." loadingSecondary='OpenApi Client is loading....' />
    )
  } else {
    return (
      <Admin
        theme={lightTheme}
        darkTheme={darkTheme}
        lightTheme={customTheme}
        dataProvider={dataProvider}
        dashboard={Dashboard}
        authProvider={authProvider(undefined, undefined, undefined, authToken, setAuthToken)}
        layout={MyLayout}
        store={localStorageStore(STORE_VERSION)}
        disableTelemetry={true}
      >
        {resourceDefinitions.map((resource) => (
          <Resource key={resource.name} {...resource} />
        ))}

        {/* ows context based mapviewer */}
        <CustomRoutes>
          <Route path="/viewer" element={<MapViewer />} />
          <Route path="/search" element={<PortalSearch />} />
        </CustomRoutes>
      </Admin>
    )
  }
}


export default MrMapFrontend