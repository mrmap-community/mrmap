import { ApartmentOutlined, DashboardOutlined, DatabaseOutlined, KeyOutlined, LoginOutlined, LogoutOutlined, UserOutlined } from '@ant-design/icons';
import { Avatar, Button, Col, Menu, Row, Tag, Tooltip } from 'antd';
import React from 'react';
import { Link, useLocation } from 'react-router-dom';

import { useAuth } from '../../Hooks/AuthUserProvider';

const { SubMenu } = Menu;

const AuthButton = (props:any) => {
  if (props.username === 'guest') {
    return (
      <Tooltip title="login">
        <Button
          type="primary"
          icon={<LoginOutlined />}
          href="/users/auth/login"
        />
      </Tooltip>
    );
  } else {
    return (
      <Tooltip title="logout">
        <Button
          type="primary"
          icon={<LogoutOutlined />}
          onClick={() => props.handleAuth({}, 'logoutUser')}
        />
      </Tooltip>
    );
  }
};

export const NavBar = () => {
  const location = useLocation();
  const [username, handleAuth] = useAuth();

  return (
    <Row justify="space-between">
      <Col>
        <Menu selectedKeys={[location.pathname]} mode="horizontal">
          <Menu.Item key="/" icon={<DashboardOutlined />} >
            <Link to="/">Dashboard</Link>
          </Menu.Item>
          <SubMenu key="users" icon={<ApartmentOutlined />} title="Users">
            <Menu.ItemGroup title="Organizations">
              <Menu.Item key="users:organizations">Organizations</Menu.Item>
            </Menu.ItemGroup>
            <Menu.ItemGroup title="Pending requests">
              <Menu.Item key="users:publish-requests">Publish requests</Menu.Item>
            </Menu.ItemGroup>
            <Menu.ItemGroup title="Users">
              <Menu.Item key="users:users" icon={<UserOutlined />}>Users</Menu.Item>
            </Menu.ItemGroup>
          </SubMenu>
          <SubMenu key="registry" icon={<DatabaseOutlined />} title="Registry">
            <Menu.ItemGroup title="Web Map Service">
              <Menu.Item key="/registry/services/wms"><Link to="/registry/services/wms">WMS</Link></Menu.Item>
              <Menu.Item key="/registry/services/layers"><Link to="/registry/services/layers">Layers</Link></Menu.Item>
            </Menu.ItemGroup>
            <Menu.ItemGroup title="Web Feature Service">
              <Menu.Item key="registry:wfs">WFS</Menu.Item>
              <Menu.Item key="registry:featuretypes">Featuretypes</Menu.Item>
              <Menu.Item key="registry:featuretype-elements">Featuretype elements</Menu.Item>
            </Menu.ItemGroup>
            <Menu.ItemGroup title="Catalouge Service">
              <Menu.Item key="registry:csw">CSW</Menu.Item>
            </Menu.ItemGroup>
            <Menu.ItemGroup title="Metadata">
              <Menu.Item key="registry:metadata">Dataset Metadata</Menu.Item>
            </Menu.ItemGroup>
            <Menu.ItemGroup title="Map Contexts">
              <Menu.Item key="registry:map-contexts">Map Contexts</Menu.Item>
            </Menu.ItemGroup>
          </SubMenu>
          <SubMenu key="security" icon={<KeyOutlined />} title="Security">
            <Menu.ItemGroup title="Service authentication">
              <Menu.Item key="security:external-auth">External Authentications</Menu.Item>
            </Menu.ItemGroup>
            <Menu.ItemGroup title="Security Proxy">
              <Menu.Item key="security:service-proxy-settings">Service proxy settings</Menu.Item>
              <Menu.Item key="security:service-access-groups">Service Access Groups</Menu.Item>
              <Menu.Item key="security:allowed-operations">Allowed Operations</Menu.Item>
            </Menu.ItemGroup>
            <Menu.ItemGroup title="Service request logging">
              <Menu.Item key="scurity:logs">Logs</Menu.Item>
            </Menu.ItemGroup>
          </SubMenu>
        </Menu>
      </Col>
      <Col>
        <Avatar icon={<UserOutlined />} />
        <Tag color="default">{username}</Tag>
        <AuthButton username={username} handleAuth={handleAuth}/>
      </Col>
    </Row>

  );
};
