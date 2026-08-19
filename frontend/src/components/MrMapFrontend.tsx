
import { deepmerge } from '@mui/utils';
import { type Operation as AxiosOperation, type OpenAPIV3 } from 'openapi-client-axios';
import { useMemo, useState, type ReactElement } from 'react';
import {
  Admin,
  CustomRoutes,
  defaultDarkTheme,
  defaultLightTheme,
  localStorageStore,
  Resource,
  type RaThemeOptions
} from 'react-admin';
import { BrowserRouter, Route } from 'react-router-dom';
import { useHttpClientContext } from '../context/HttpClientContext';
import CreateGuesser from '../jsonapi/components/CreateGuesser';
import EditGuesser from '../jsonapi/components/EditGuesser';
import ListGuesser from '../jsonapi/components/ListGuesser';
import { getResourceSchema } from '../jsonapi/openapi/parser';
import authProviderFunc from '../providers/authProvider';
import jsonApiDataProvider from '../providers/dataProvider';
import i18nProvider from '../providers/i18nProvider';
import MapViewer from './MapViewer/MapViewer';
import PortalSearch from './PortalSearch/PortalSearch';
import CatalogueServiceClient from './Resource/CatalogueService/CatalogueServiceClient';
import defaultRecordRepresentation from './Resource/defaultRecordRepresentation';
import RESOURCES from './Resource/Definition';


import Dashboard from './Dashboard/Dashboard';
import MyLayout from './Layout/Layout';
import LoadingOpenApi from './Loading/LoadingOpenApi';

const STORE_VERSION = '1'
const store = localStorageStore(STORE_VERSION)

const lightTheme = defaultLightTheme
const darkTheme: RaThemeOptions = deepmerge(defaultDarkTheme, {
  palette: { 
    mode: 'dark' 
  } 
})


const MrMapFrontend = (): ReactElement => {
  const [loadingAnimationComplete, setLoadingAnimationComplete] = useState(false);
  const { api, isPending } = useHttpClientContext()
  const dataProvider = useMemo(() => {
    return api && jsonApiDataProvider({
      httpClient: api, 
    })
  }, [api])
  
  const authProvider = useMemo(()=>{
    return authProviderFunc()
  },[])

  const resourceDefinitions = useMemo(() => {
    return RESOURCES.map((resource)=> {
      const showOperationName = `retreive_${resource.name}`
      const createOperationName = `create_${resource.name}`
      const editOperationName = `partial_update_${resource.name}`
      const listOperationName =`list_${resource.name}`
      const deleteOperationName =`destroy_${resource.name}`

      const createOperation = api?.getOperation(createOperationName)
      const editOperation = api?.getOperation(editOperationName)
      const listOperation = api?.getOperation(listOperationName)
      const deleteOperation = api?.getOperation(deleteOperationName)

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
        ...({options: {
              ...resource.options, 
              showOperationName: showOperationName,
              createOperationName: createOperationName,
              editOperationName: editOperationName,
              listOperationName: listOperationName,
              hasDelete: !!deleteOperation,
              label: resource.name,
            }}),
        ...resource,
        
      }
    })
  }, [api])

  const resources = useMemo(()=> (
    resourceDefinitions.map((resource) => (
          <Resource key={resource.name} {...resource} />
        ))
  ),[resourceDefinitions])

  const isApplicationReady =
    !isPending &&
    dataProvider !== undefined &&
    resources.length > 0;
  
  if (!loadingAnimationComplete) {
    return (
      <LoadingOpenApi
        canComplete={isApplicationReady}
        onComplete={() => setLoadingAnimationComplete(true)}
      />
    );
  }
  return (
    <BrowserRouter>
      <Admin
        theme={lightTheme}
        darkTheme={darkTheme}
        lightTheme={lightTheme}
        dataProvider={dataProvider}
        authProvider={authProvider}
        i18nProvider={i18nProvider}
        dashboard={Dashboard}
        layout={MyLayout}
        store={store}
        disableTelemetry
        requireAuth
      >
        {resources}

        {/* ows context based mapviewer */}
        {
          <CustomRoutes >
            <Route path="/csw-client" element={<CatalogueServiceClient />} />
            <Route path="/viewer" element={<MapViewer />} />
            <Route path="/search" element={<PortalSearch />} />
          </CustomRoutes>
        } 
      </Admin>
    </BrowserRouter>
  )
  
}

export default MrMapFrontend