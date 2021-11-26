import './App.css';

import { ApiOutlined, GithubOutlined } from '@ant-design/icons';
import { Layout, Space } from 'antd';
import React, { useState } from 'react';
import { BrowserRouter as Router, Navigate, Outlet, Route, Routes } from 'react-router-dom';

import { Dashboard } from './Components/Dashboard/Dashboard';
import { MapContextList } from './Components/MapContext/MapContextList/MapContextList';
import { FormSteps } from './Components/MapContextForm/MapContextForm';
import { NavBar } from './Components/NavBar/NavBar';
import { ServiceEdit } from './Components/Service/ServiceEdit';
import { ServiceList } from './Components/Service/ServiceList/ServiceList';
import { Login } from './Components/Users/Auth/Login';
import { Logout } from './Components/Users/Auth/Logout';
import { AuthProvider, useAuth } from './Hooks/AuthContextProvider';
import logo from './logo.png';

const { Content, Footer, Sider } = Layout;

function RequireAuth ({ children }: { children: JSX.Element }) {
  const auth = useAuth();
  debugger;
  if (!auth.user) {
    return <Navigate to='/login' />;
  }
  return children;
}

export default function App (): JSX.Element {
  if (process.env.REACT_APP_REST_API_SCHEMA_URL === undefined) {
    throw new Error('Environment variable REACT_APP_REST_API_SCHEMA_URL is undefined.');
  }
  if (process.env.REACT_APP_REST_API_BASE_URL === undefined) {
    throw new Error('Environment variable REACT_APP_REST_API_BASE_URL is undefined.');
  }
  const swaggerUiUrl = process.env.REACT_APP_REST_API_SCHEMA_URL + 'swagger-ui/';

  const [collapsed, setCollapsed] = useState(false);

  const onCollapse = (collapsed: boolean) => {
    setCollapsed(collapsed);
  };

  return (
    <Router>
      <AuthProvider>
        <Routes>
          <Route
            path='/login'
            element={<Login />}
          />
          <Route
            path='/logout'
            element={<RequireAuth><Logout /></RequireAuth>}
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
                  <NavBar />
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
              path='/'
              element={<Dashboard />}
            />
            <Route
              path='/registry/services/wms'
              element={<ServiceList />}
            />
            <Route
              path='/registry/services/add'
              element={<ServiceEdit />}
            />
            <Route
              path='/registry/mapcontexts'
              element={<MapContextList />}
            />
            <Route
              path='/registry/mapcontexts/add'
              element={<FormSteps />}
            />
          </Route>
        </Routes>
      </AuthProvider>
    </Router>
  );
}
