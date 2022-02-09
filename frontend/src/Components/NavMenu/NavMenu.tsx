import React, { ReactElement } from 'react';

import { DashboardOutlined, DatabaseOutlined, LogoutOutlined, SecurityScanOutlined, UserOutlined } from '@ant-design/icons';
import { Menu } from 'antd';
import { Link, useLocation } from 'react-router-dom';

import { useAuth } from '../../Hooks/useAuth';


const { SubMenu } = Menu;

// submenu keys of first level
const rootSubmenuKeys = ['users', 'registry', 'security'];

export const NavMenu = (): ReactElement => {
  const location = useLocation();
  const auth = useAuth();

  const [openKeys, setOpenKeys] = React.useState(['/']);

  const onOpenChange = (keys: string[]) => {
    const latestOpenKey = keys.find(key => openKeys.indexOf(key) === -1);
    if (latestOpenKey === undefined || rootSubmenuKeys.indexOf(latestOpenKey) === -1) {
      setOpenKeys(keys);
    } else {
      setOpenKeys(latestOpenKey ? [latestOpenKey] : []);
    }
  };

  return (
    <Menu
      theme='dark'
      selectedKeys={[location.pathname]}
      openKeys={openKeys} onOpenChange={onOpenChange}
      mode='inline'
    >
      <Menu.Item
        key='/'
        icon={<DashboardOutlined />}
      >
        <Link to='/'>Dashboard</Link>
      </Menu.Item>
      <SubMenu
        key='auth'
        icon={<UserOutlined />}
        title='Auth'
      >
        <Menu.Item key='auth:users'>Users</Menu.Item>
        <Menu.Item key='auth:organizations'>Organizations</Menu.Item>
        <Menu.Item key='auth:publish-requests'>Publish requests</Menu.Item>
      </SubMenu>
      <SubMenu
        key='registry'
        icon={<DatabaseOutlined />}
        title='Registry'
      >
        <Menu.Item key='/registry/services/wms'><Link to='/registry/services/wms'>WMS</Link></Menu.Item>
        <Menu.Item key='/registry/services/wfs'><Link to='/registry/services/wfs'>WFS</Link></Menu.Item>
        <Menu.Item key='/registry/services/csw'><Link to='/registry/services/csw'>CSW</Link></Menu.Item>
        <Menu.Item key='/registry/layers'><Link to='/registry/layers'>Layers</Link></Menu.Item>
        <Menu.Item key='/registry/featuretypes'><Link to='/registry/featuretypes'>Feature Types</Link></Menu.Item>
        <Menu.Item key='/registry/dataset-metadata'>
          <Link to='/registry/dataset-metadata'>Dataset Metadata</Link>
        </Menu.Item>
        <Menu.Item key='/registry/mapcontexts'><Link to='/registry/mapcontexts'>Map Contexts</Link></Menu.Item>
      </SubMenu>
      <SubMenu
        key='security'
        icon={<SecurityScanOutlined />}
        title='Security'
      >
        <Menu.Item key='security:external-auth'>External Authentications</Menu.Item>
        <Menu.Item key='security:service-proxy-settings'>Service proxy settings</Menu.Item>
        <Menu.Item key='security:service-access-groups'>Service Access Groups</Menu.Item>
        <Menu.Item key='security:allowed-operations'>Allowed Operations</Menu.Item>
        <Menu.Item key='security:logs'>Logs</Menu.Item>
      </SubMenu>
      <Menu.Item
        key='logout'
        icon={<LogoutOutlined />}
      >
        <Link to='/logout'>Logout ({auth?.user.username})</Link>
      </Menu.Item>
    </Menu>
  );
};
