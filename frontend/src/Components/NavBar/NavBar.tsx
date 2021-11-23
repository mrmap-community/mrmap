import { Avatar, Button, Col, Menu, Row, Tag, Tooltip } from 'antd';
import { LoginOutlined, LogoutOutlined, DashboardOutlined, UserOutlined, DatabaseOutlined, KeyOutlined, SecurityScanOutlined } from '@ant-design/icons';
import { Link } from "react-router-dom";
import { useLocation } from 'react-router-dom';
import { useAuth } from '../../Hooks/AuthUserProvider';

const { SubMenu } = Menu;

const AuthButton = (props: any) => {
  if (props.username === "guest") {
    return <Tooltip title="login"><Button type="primary" icon={<LoginOutlined />} href="/users/auth/login" /></Tooltip>
  } else {
    return <Tooltip title="logout"><Button type="primary" icon={<LogoutOutlined />} onClick={() => props.handleAuth({}, "logoutUser")} /></Tooltip>
  }
}

export const NavBar = () => {
  const location = useLocation();
  const [username, handleAuth] = useAuth();

  return (
    <Menu theme="dark" selectedKeys={[location.pathname]} mode="inline">
      <Menu.Item key="/" icon={<DashboardOutlined />} >
        <Link to="/">Dashboard</Link>
      </Menu.Item>
      <SubMenu key="users" icon={<UserOutlined />} title="Users">
        <Menu.Item key="users:users">Users</Menu.Item>
        <Menu.Item key="users:organizations">Organizations</Menu.Item>
        <Menu.Item key="users:publish-requests">Publish requests</Menu.Item>
      </SubMenu>
      <SubMenu key="registry" icon={<DatabaseOutlined />} title="Registry">
        <Menu.Item key="/registry/services/wms"><Link to="/registry/services/wms">WMS</Link></Menu.Item>
        <Menu.Item key="registry:wfs">WFS</Menu.Item>
        <Menu.Item key="registry:csw">CSW</Menu.Item>
        <Menu.Item key="/registry/services/layers"><Link to="/registry/services/layers">Layers</Link></Menu.Item>
        <Menu.Item key="registry:featuretypes">Feature Types</Menu.Item>
        <Menu.Item key="registry:metadata">Metadata Records</Menu.Item>
        <Menu.Item key="registry:map-contexts">Map Contexts</Menu.Item>
      </SubMenu>
      <SubMenu key="security" icon={<SecurityScanOutlined />} title="Security">
        <Menu.Item key="security:external-auth">External Authentications</Menu.Item>
        <Menu.Item key="security:service-proxy-settings">Service proxy settings</Menu.Item>
        <Menu.Item key="security:service-access-groups">Service Access Groups</Menu.Item>
        <Menu.Item key="security:allowed-operations">Allowed Operations</Menu.Item>
        <Menu.Item key="scurity:logs">Logs</Menu.Item>
      </SubMenu>
    </Menu>
    // <Avatar icon={<UserOutlined />} />
    // <Tag color="default">{username}</Tag>
    // <AuthButton username={username} handleAuth={handleAuth}/>
  );
}