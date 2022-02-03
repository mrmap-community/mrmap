import { ApiOutlined, GithubOutlined } from '@ant-design/icons';
import { Layout, Space } from 'antd';
import React, { useState } from 'react';
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
import { TaskProgressList } from './Components/TaskProgressList/TaskProgressList';
import WfsTable from './Components/WfsTable/WfsTable';
import { WmsSecuritySettings } from './Components/WmsSecuritySettings/WmsSecuritySettings';
import WmsTable from './Components/WmsTable/WmsTable';
import { useAuth } from './Hooks/useAuth';
import logo from './logo.png';
import CatalogueServiceRepo from './Repos/CswRepo';
import WebFeatureServiceRepo from './Repos/WfsRepo';
import WebMapServiceRepo from './Repos/WmsRepo';


const { Content, Footer, Sider } = Layout;

function RequireAuth ({ children }:{ children: JSX.Element }) {
  const auth = useAuth();
  const location = useLocation();
  if (!auth || !auth.userId) {
    // store location so login page can forward to original page
    return <Navigate to='/login' state={{ from: location }} />;
  }
  return children;
}

export default function App (): JSX.Element {
  const swaggerUiUrl = '/swagger-ui/';

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
              <Layout style={{ minHeight: '100vh' }}>
                <Sider
                  collapsible
                  collapsed={collapsed}
                  onCollapse={onCollapse}>
                  <div className='logo'>
                    <img
                      src={logo}
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
                  <Footer style={{ textAlign: 'center' }}>
                    <Space>
                      <a href={swaggerUiUrl}><ApiOutlined /> OpenAPI</a>
                      <a href='https://github.com/mrmap-community/mrmap'><GithubOutlined /> GitHub</a>
                    </Space>
                  </Footer>
                </Layout>
              </Layout>
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
            element={<RegisterServiceForm repo={new WebMapServiceRepo()} />}
          />
          <Route
            path='/registry/services/wms/:id/security/*'
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
