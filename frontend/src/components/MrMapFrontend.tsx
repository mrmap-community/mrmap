import { useMemo, type ReactElement } from 'react';
import {
  Admin,
  CustomRoutes,
  defaultTheme,
  Loading,
  localStorageStore,
  Resource,
  useTheme,
  type RaThemeOptions
} from 'react-admin';
import { BrowserRouter, Route } from 'react-router-dom';

import { type Operation as AxiosOperation, type OpenAPIV3 } from 'openapi-client-axios';

import { Card, Grid, IconButton, Tooltip, Typography } from '@mui/material';
import { useHttpClientContext } from '../context/HttpClientContext';
import CreateGuesser from '../jsonapi/components/CreateGuesser';
import EditGuesser from '../jsonapi/components/EditGuesser';
import ListGuesser from '../jsonapi/components/ListGuesser';
import { getResourceSchema } from '../jsonapi/openapi/parser';
import authProviderFunc from '../providers/authProvider';
import jsonApiDataProvider from '../providers/dataProvider';
import i18nProvider from '../providers/i18nProvider';
import Dashboard from './Dashboard/Dashboard';
import MyLayout from './Layout/Layout';
import MapViewer from './MapViewer/MapViewer';
import PortalSearch from './PortalSearch/PortalSearch';
import CatalogueServiceClient from './Resource/CatalogueService/CatalogueServiceClient';
import defaultRecordRepresentation from './Resource/defaultRecordRepresentation';
import RESOURCES from './Resource/Definition';

import CircleIcon from '@mui/icons-material/Circle';
import GitHubIcon from '@mui/icons-material/GitHub';
import { ReadyState } from 'react-use-websocket';
import { useSystemTime } from '../jsonapi/hooks/useSystemTime';

const STORE_VERSION = '1'
const store = localStorageStore(STORE_VERSION)
const lightTheme = defaultTheme
const customTheme: RaThemeOptions = { ...defaultTheme, transitions: {} }
const darkTheme: RaThemeOptions = { ...defaultTheme, palette: { mode: 'dark' } }

const MrMapFrontend = (): ReactElement => {
  const { api, isPending, realtimeIsReady } = useHttpClientContext()
      const systemTime = useSystemTime();
    const theme = useTheme();
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


  
    const readyStateColor = useMemo(()=>{
      switch(realtimeIsReady){
        case ReadyState.CONNECTING:
          return 'warning'
        case ReadyState.OPEN:
          return 'success'
        case ReadyState.CLOSING:
        case ReadyState.CLOSED:
          return 'error'
        case ReadyState.UNINSTANTIATED:
        default:
          return 'info'
  
      }
    },[realtimeIsReady])
  
  
  if (isPending || dataProvider === undefined || resources.length === 0) {
    return (
      <Loading loadingPrimary="Initialize...." loadingSecondary='OpenApi Client is loading....' />
    )
  } else {
    return (
      <BrowserRouter>
        <Admin
          theme={lightTheme}
          darkTheme={darkTheme}
          lightTheme={customTheme}
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
          <CustomRoutes >
            <Route path="/csw-client" element={<CatalogueServiceClient />} />
            <Route path="/viewer" element={<MapViewer />} />
            <Route path="/search" element={<PortalSearch />} />
          </CustomRoutes>
            
        </Admin>
         <Card style={{
              position: 'fixed',
              right: 0, 
              bottom: 0, 
              left: 0, 
              zIndex: 100,
        }}>
          <Grid container spacing={2} sx={{ justifyContent: 'space-between' }}>
          
            <Grid >
              <Typography padding={1}> 
                v.{api?.document.info.version}
              </Typography>
            </Grid>

            <Grid  >
              <IconButton 
                href="https://github.com/mrmap-community" 
                target="_blank"
              >
                <GitHubIcon />
              </IconButton>
            </Grid>

            <Grid 
              container 
              alignItems="center"  
              justifyContent='space-between'>
              <Grid>
                <Typography>{systemTime ?? ''}</Typography>
              </Grid>
              <Grid>
                <Tooltip title={
                  realtimeIsReady === ReadyState.OPEN 
                  ? 'Backend is connected'
                  : 'Connection to backend lost'
                  }
                >
                  <IconButton>
                    <CircleIcon color={readyStateColor}/>
                  </IconButton>
                </Tooltip>
              </Grid>
            </Grid>
          
          </Grid>
        </Card>
      </BrowserRouter>
    )
  }
}


export default MrMapFrontend
