import { MapContext } from '@terrestris/react-geo';
import { Layout } from 'antd';
import React, { useState } from 'react';
import { useSelector } from 'react-redux';
import { BrowserRouter as Router, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import './App.css';
import CswTable from './Components/CswTable/CswTable';
import { Dashboard } from './Components/Dashboard/Dashboard';
import DatasetMetadataTable from './Components/DatasetMetadataTable/DatasetMetadataTable';
import FeatureTypeTable from './Components/FeatureTypeTable/FeatureTypeTable';
import LayerTable from './Components/LayerTable/LayerTable';
import { Login } from './Components/LoginForm/LoginForm';
import { Logout } from './Components/Logout/Logout';
import { MapContextForm } from './Components/MapContextForm/MapContextForm';
import MapContextTable from './Components/MapContextTable/MapContextTable';
import { NavMenu } from './Components/NavMenu/NavMenu';
import { PageNotFound } from './Components/PageNotFound/PageNotFound';
import RegisterServiceForm from './Components/RegisterServiceForm/RegisterServiceForm';
import RepoSelect from './Components/Shared/RepoSelect/RepoSelect';
import { TaskProgressList } from './Components/TaskProgressList/TaskProgressList';
import WfsTable from './Components/WfsTable/WfsTable';
import { WmsSecuritySettings } from './Components/WmsSecuritySettings/WmsSecuritySettings';
import WmsTable from './Components/WmsTable/WmsTable';
import CatalogueServiceRepo from './Repos/CswRepo';
import WebFeatureServiceRepo from './Repos/WfsRepo';
import { currentUserSelectors } from './Services/ReduxStore/Reducers/CurrentUser';
import WebSockets from './Services/WebSockets';
import { olMap } from './Utils/MapUtils';

const { Content, Sider } = Layout;

function RequireAuth ({ children }:{ children: JSX.Element }) {
  const location = useLocation();
  const currentUser = useSelector(currentUserSelectors.selectAll);
  
  if (!currentUser || !currentUser[0]) {
    // store location so login page can forward to original page
    return <Navigate to='/login' state={{ from: location }} />;
  }
  return children;
}

export default function App (): JSX.Element {

  const [collapsed, setCollapsed] = useState(false);

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
                      style={{ zIndex: 1001 }}
                    >
                      <div className='logo'>
                        <img
                          src={process.env.PUBLIC_URL + '/logo.png'}
                          alt='Mr. Map Logo'
                        >
                        </img>
                      </div>
                      <NavMenu />
                    </Sider>
                    <Layout className='site-layout'>
                      <Content style={{ margin: '0 16px' }}>
                        <div
                          className='site-layout-background'
                          style={{ padding: 24, minHeight: 360 }}
                        >
                          <Outlet />
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
            path='/notify'
            element={<TaskProgressList />}
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
            element={<RepoSelect resourceType='WebMapService' />}
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
            element={<RegisterServiceForm repo={new WebFeatureServiceRepo()} />}
          />
          <Route
            path='/registry/services/csw'
            element={<CswTable />}
          />
          <Route
            path='/registry/services/csw/add'
            element={<RegisterServiceForm repo={new CatalogueServiceRepo()} />}
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
            element={<MapContextForm />}
          />
          <Route
            path='/registry/mapcontexts/:id/edit'
            element={<MapContextForm />}
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
