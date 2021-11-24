import './App.css';

import { ApiOutlined, GithubOutlined } from '@ant-design/icons';
import { Layout, Space } from 'antd';
import React, { useState } from 'react';
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';

import { Dashboard } from './Components/Dashboard/Dashboard';
import { MapContextList } from './Components/MapContext/MapContextList/MapContextList';
import { MapContextForm } from './Components/MapContextForm/MapContextForm';
import { NavBar } from './Components/NavBar/NavBar';
import { ServiceEdit } from './Components/Service/ServiceEdit';
import { ServiceList } from './Components/Service/ServiceList/ServiceList';
import { LoginForm } from './Components/Users/Auth/Login';
import { AuthProvider } from './Hooks/AuthUserProvider';
import logo from './logo.png';

const { Content, Footer, Sider } = Layout;

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
                <Routes>
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
                    path='/users/auth/login'
                    element={<LoginForm />}
                  />
                  <Route
                    path='/registry/mapcontexts'
                    element={<MapContextList/>}
                  />
                  <Route
                    path='/registry/mapcontexts/add'
                    element={<MapContextForm/>}
                  />
                </Routes>
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
      </AuthProvider>
    </Router>
  );
}
