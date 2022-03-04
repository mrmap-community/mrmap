import { MapContext } from '@terrestris/react-geo';
import { Divider, Layout } from 'antd';
import React, { useState } from 'react';
import { BrowserRouter as Router, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import './App.css';
import BackgroundProcessTable from './Components/BackgroundProcessTable/table';
import CswTable from './Components/CswTable/CswTable';
import { Dashboard } from './Components/Dashboard/Dashboard';
import DatasetMetadataTable from './Components/DatasetMetadataTable/DatasetMetadataTable';
import FeatureTypeTable from './Components/FeatureTypeTable/FeatureTypeTable';
import LayerTable from './Components/LayerTable/LayerTable';
import { Login } from './Components/LoginForm/LoginForm';
import { Logout } from './Components/Logout/Logout';
import { MapContextEditor } from './Components/MapContextEditor/MapContextEditor';
import MapContextTable from './Components/MapContextTable/MapContextTable';
import { NavMenu } from './Components/NavMenu/NavMenu';
import { PageNotFound } from './Components/PageNotFound/PageNotFound';
import RepoForm from './Components/Shared/RepoForm/RepoForm';
import WfsTable from './Components/WfsTable/WfsTable';
import { WmsSecuritySettings } from './Components/WmsSecuritySettings/WmsSecuritySettings';
import WmsTable from './Components/WmsTable/WmsTable';
import { store } from './Services/ReduxStore/Store';
import WebSockets from './Services/WebSockets';
import { olMap } from './Utils/MapUtils';

const { Content, Sider } = Layout;

function RequireAuth ({ children }:{ children: JSX.Element }) {
  const location = useLocation();
  const currentUser = store.getState().currentUser.user;

  if (!currentUser)
  {
    // store location so login page can forward to original page
    return <Navigate to='/login' state={{ from: location }} />;
  }
  return children;
}

export default function App (): JSX.Element {

  const [collapsed, setCollapsed] = useState<boolean>(false);

  const onCollapse = (_collapsed: boolean) => {
    setCollapsed(_collapsed);
  };

  return (
    <Router>
      <Routes>
        <Route
          path='/login'
          element={<Login />}
        />
        <Route
          path='/logout'
          element={<Logout />}
        />
        <Route
          path='/'
          element={
            <RequireAuth>
              <>
                <WebSockets />
                <MapContext.Provider value={olMap}>
                  <Layout style={{ minHeight: '100vh' }}>
                    <Sider
                      collapsible
                      collapsed={collapsed}
                      onCollapse={onCollapse}
                      style={{ 
                        zIndex: 1001,  
                        overflow: 'auto',
                        height: '100vh',
                        position: 'fixed',
                      }}
                      theme='light'
                    >
                      
                      <div className='logo'>
                        <img
                          src={process.env.PUBLIC_URL + '/logo.png'}
                          alt='Mr. Map Logo'
                        >
                        </img>
                      </div>
                      <Divider />
                      <NavMenu collapsed={collapsed}/>
                      <Divider />
                      
                    </Sider>
                    <Layout 
                      className='site-layout' 
                      style={{ 
                        marginLeft: collapsed? 80: 200,
                      }}
                    >

                      <Content >
                        <div
                          className='site-layout-background'
                          style={{ padding: 24 }}
                        >
                          <Outlet/>
                        </div>
                      </Content>
                    </Layout>
                  </Layout>
                </MapContext.Provider>
              </>
            </RequireAuth>
          }
        >
          <Route
            path='/notify/background-processes'
            element={<BackgroundProcessTable />}
          />
          <Route
            path='/'
            element={<Dashboard />}
          />
          <Route
            path='/registry/services/wms'
            element={<WmsTable />}
          />
          <Route
            path='/registry/services/wms/add'
            element={<RepoForm resourceType='WebMapService'/>}
          />
          <Route
            path='/registry/services/wms/:wmsId/security/*'
            element={<WmsSecuritySettings />}
          />
          <Route
            path='/registry/services/wfs'
            element={<WfsTable />}
          />
          <Route
            path='/registry/services/wfs/add'
            element={<RepoForm resourceType='WebFeatureService'/>}
          />
          <Route
            path='/registry/services/csw'
            element={<CswTable />}
          />
          <Route
            path='/registry/services/csw/add'
            element={<RepoForm resourceType='CatalougeService'/>}
          />
          <Route
            path='/registry/layers'
            element={<LayerTable />}
          />
          <Route
            path='/registry/featuretypes'
            element={<FeatureTypeTable />}
          />
          <Route
            path='/registry/dataset-metadata'
            element={<DatasetMetadataTable />}
          />
          <Route
            path='/registry/mapcontexts'
            element={<MapContextTable />}
          />
          <Route
            path='/registry/mapcontexts/add'
            element={<MapContextEditor />}
          />
          <Route
            path='/registry/mapcontexts/:id/edit'
            element={<MapContextEditor />}
            // @ts-ignore
            exact
          />
          <Route
            path='*'
            element={<PageNotFound/>}
          />
        </Route>
      </Routes>
    </Router>
  );
}
