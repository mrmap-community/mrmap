import { Dashboard } from "./Components/Dashboard/Dashboard";
import { ServiceList } from "./Components/Service/ServiceList/ServiceList";
import { NavBar } from "./Components/NavBar/NavBar";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import './App.css';
import { OpenAPIProvider } from "./Hooks/OpenAPIProvider";
import { LoginForm } from "./Components/Users/Auth/Login";
import { AuthProvider } from "./Hooks/AuthUserProvider";
import { ServiceEdit } from "./Components/Service/ServiceEdit";
import { Layout, Menu } from 'antd';
import { useState } from "react";
import logo from "./logo.png";

const { Header, Content, Footer, Sider } = Layout;
const { SubMenu } = Menu;

export default function App() {

  if (process.env.REACT_APP_REST_API_SCHEMA_URL === undefined) {
    throw new Error("Environment variable REACT_APP_REST_API_SCHEMA_URL is undefined.");
  }
  if (process.env.REACT_APP_REST_API_BASE_URL === undefined) {
    throw new Error("Environment variable REACT_APP_REST_API_BASE_URL is undefined.");
  }

  const [collapsed, setCollapsed] = useState(false);

  const onCollapse = (collapsed: boolean) => {
    console.log(collapsed);
    setCollapsed(collapsed);
  };

  return (
    <Router>
      <OpenAPIProvider definition={process.env.REACT_APP_REST_API_SCHEMA_URL} axiosConfigDefaults={{ baseURL: process.env.REACT_APP_REST_API_BASE_URL }}>
        <AuthProvider>
          <Layout style={{ minHeight: '100vh' }}>
            <Sider collapsible collapsed={collapsed} onCollapse={onCollapse}>
              <div className="logo">
                <img src={logo}></img>
              </div>
              <NavBar />
              {/* <Menu theme="dark" defaultSelectedKeys={['1']} mode="inline">
                <Menu.Item key="1" icon={<PieChartOutlined />}>
                  Option 1
                </Menu.Item>
                <Menu.Item key="2" icon={<DesktopOutlined />}>
                  Option 2
                </Menu.Item>
                <SubMenu key="sub1" icon={<UserOutlined />} title="User">
                  <Menu.Item key="3">Tom</Menu.Item>
                  <Menu.Item key="4">Bill</Menu.Item>
                  <Menu.Item key="5">Alex</Menu.Item>
                </SubMenu>
                <SubMenu key="sub2" icon={<TeamOutlined />} title="Team">
                  <Menu.Item key="6">Team 1</Menu.Item>
                  <Menu.Item key="8">Team 2</Menu.Item>
                </SubMenu>
                <Menu.Item key="9" icon={<FileOutlined />}>
                  Files
                </Menu.Item>
              </Menu> */}
            </Sider>
            <Layout className="site-layout">
              <Content style={{ margin: '0 16px' }}>
                <div className="site-layout-background" style={{ padding: 24, minHeight: 360 }}>
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/registry/services/wms" element={<ServiceList />} />
                    <Route path="/registry/services/add" element={<ServiceEdit />} />
                    <Route path="/users/auth/login" element={<LoginForm />} />
                  </Routes>
                </div>
              </Content>
              <Footer style={{ textAlign: 'center' }}>Mr. Map 1.0-pre <a href="https://github.com/mrmap-community/mrmap">GitHub</a></Footer>
            </Layout>
          </Layout>
        </AuthProvider>
      </OpenAPIProvider>
    </Router>
  );
}