import { Dashboard } from "./Components/Dashboard/Dashboard";
import { ServiceList } from "./Components/Service/ServiceList/ServiceList";
import { NavBar } from "./Components/NavBar/NavBar";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import './App.css';
import { LoginForm } from "./Components/Users/Auth/Login";
import { AuthProvider } from "./Hooks/AuthUserProvider";
import { ServiceEdit } from "./Components/Service/ServiceEdit";
import { Layout, Space } from 'antd';
import { useState } from "react";
import logo from "./logo.png";
import { ApiOutlined, GithubOutlined } from "@ant-design/icons";

const { Content, Footer, Sider } = Layout;

export default function App() {

  if (process.env.REACT_APP_REST_API_SCHEMA_URL === undefined) {
    throw new Error('Environment variable REACT_APP_REST_API_SCHEMA_URL is undefined.');
  }
  if (process.env.REACT_APP_REST_API_BASE_URL === undefined) {
    throw new Error('Environment variable REACT_APP_REST_API_BASE_URL is undefined.');
  }
  const swaggerUiUrl = process.env.REACT_APP_REST_API_SCHEMA_URL + "swagger-ui/";

  const [collapsed, setCollapsed] = useState(false);

  const onCollapse = (collapsed: boolean) => {
    console.log(collapsed);
    setCollapsed(collapsed);
  };

  return (
    <Router>
      <AuthProvider>
        <Layout style={{ minHeight: '100vh' }}>
          <Sider collapsible collapsed={collapsed} onCollapse={onCollapse}>
            <div className="logo">
              <img src={logo} alt="Mr. Map Logo"></img>
            </div>
            <NavBar />
          </Sider>
          <Layout className="site-layout">
            <Content style={{ margin: '0 16px' }}>
              <div className="site-layout-background" style={{ padding: 24, minHeight: 360 }}>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/registry/services/wms" element={<ServiceList />} />
                  <Route path="/registry/services/add" element={<ServiceEdit />} />
                  <Route path="/users/auth/login" element={<LoginForm />} />
                  <Route path="/registry/mapcontext/add" element={<MapContextForm/>}/>
                </Routes>
              </div>
            </Content>
            <Footer style={{ textAlign: 'center' }}>
              <Space>
                <a href={swaggerUiUrl}><ApiOutlined /> OpenAPI</a>
                <a href="https://github.com/mrmap-community/mrmap"><GithubOutlined /> GitHub</a>
              </Space>
            </Footer>
          </Layout>
        </Layout>
      </AuthProvider>
    </Router>
  );
}
