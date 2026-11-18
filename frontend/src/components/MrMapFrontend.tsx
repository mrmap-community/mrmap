
import { useMemo, useState, type ReactElement } from 'react';
import {
  Admin,
  Authenticated,
  CustomRoutes,
  defaultDarkTheme,
  defaultLightTheme,
  localStorageStore,
  Resource,
  type RaThemeOptions
} from 'react-admin';
import { BrowserRouter, Route } from 'react-router-dom';

import { deepmerge } from '@mui/utils';

import { useHttpClientContext } from '../context/HttpClientContext';
import ListGuesser from '../jsonapi/components/ListGuesser';
import ListWithDialogs from '../jsonapi/components/ListWithDialogs';
import { getRelatedResourceType, indexRelatedOperations } from '../jsonapi/openapi/parser';
import authProviderFunc from '../providers/authProvider';
import jsonApiDataProvider from '../providers/dataProvider';
import i18nProvider from '../providers/i18nProvider';
import Dashboard from './Dashboard/Dashboard';
import MyLayout from './Layout/Layout';
import MrMapLoginPage from './Layout/LoginPage';
import LoadingOpenApi from './Loading/LoadingOpenApi';
import MapViewer from './MapViewer/MapViewer';
import PortalSearch from './PortalSearch/PortalSearch';
import defaultRecordRepresentation from './Resource/defaultRecordRepresentation';
import RESOURCES from './Resource/Definition';
import HistoryList from './Resource/Generic/History/HistoryList';
import MetadataEditorRoute from './Resource/Generic/MetadataEditor/MetadataEditorRoute';
import ServiceExplorer from './Resource/ServiceExplorer/ServiceExplorer';

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
    const relatedOperations = indexRelatedOperations(api?.getOperations() ?? []);
    return RESOURCES.map((resource)=> {
      const createOperationName = `create_${resource.name}`
      const editOperationName = `partial_update_${resource.name}`
      const listOperationName =`list_${resource.name}`
      const deleteOperationName =`destroy_${resource.name}`

      const createOperation = api?.getOperation(createOperationName)
      const editOperation = api?.getOperation(editOperationName)
      const listOperation = api?.getOperation(listOperationName)
      const deleteOperation = api?.getOperation(deleteOperationName)

      const related_list_operations = relatedOperations.get(resource.name) ?? []
      // the parser answers which JSON:API type a nested list carries; a nested
      // operation without one is no resource to route to
      const related_list_resources = related_list_operations
        .map((schema) => getRelatedResourceType(schema))
        .filter((relatedResourceType): relatedResourceType is string => relatedResourceType !== undefined)
      const related_routes = related_list_resources.map((relatedResource) => <Route key={`nested-${relatedResource}-of-${resource.name}`} path={`:${relatedResource}id/${relatedResource}`} element={<ListGuesser resource={relatedResource} relatedResource={{resource: resource.name}}> </ListGuesser>}></Route>)
      // "View all history" of the compact feeds navigates to this paginated and filterable changelog.
      const history_routes = api?.getOperation(`list_Historical${resource.name}`)
        ? [<Route key={`history-${resource.name}`} path="history" element={<HistoryList />}></Route>]
        : []

      return {
        ...(resource.create || createOperation && { hasCreate: true}),
        ...(resource.list || listOperation && {list: ListWithDialogs, hasList: true}),
        ...(resource.edit || editOperation && { hasEdit: true}),
        // FUTURE: merge children and related_list_operations paths
        ...(resource.children || { 
          children: [...related_routes, ...history_routes]
        }) as ReactElement[],
        recordRepresentation: resource.recordRepresentation ? resource.recordRepresentation : defaultRecordRepresentation,
        ...resource,
        options: {
              hasDelete: !!deleteOperation,
              label: resource.name,
              ...resource.options, 
            },
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
        loginPage={MrMapLoginPage}
        dashboard={Dashboard}
        layout={MyLayout}
        store={store}
        disableTelemetry
      >
        {resources}

        {/* the screens of #833: the resource routes above answer the public
            read-only list and show of published services to an anonymous
            visitor, so the Admin no longer guards every route with
            `requireAuth`. Everything behind a session - the dashboard, the
            explorer, the viewer, the search and the metadata editor - guards
            itself here with <Authenticated> or in its controller, and the
            backend keeps enforcing every record either way. */}
        {
          <CustomRoutes >
            <Route path="/viewer" element={<Authenticated><MapViewer /></Authenticated>} />
            <Route path="/service-explorer" element={<Authenticated><ServiceExplorer /></Authenticated>} />
            <Route path="/search" element={<Authenticated><PortalSearch /></Authenticated>} />
            {/* full screen record editor (#1245); :type is the JSON:API name */}
            <Route
              path="/metadata/:type/:id/edit"
              element={<Authenticated><MetadataEditorRoute /></Authenticated>}
            />
          </CustomRoutes>
        } 
      </Admin>
    </BrowserRouter>
  )
  
}

export default MrMapFrontend
