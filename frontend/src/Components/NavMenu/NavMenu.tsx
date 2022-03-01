import { DashboardOutlined, DatabaseOutlined, LogoutOutlined, SecurityScanOutlined, UnorderedListOutlined, UserOutlined } from '@ant-design/icons';
import { Badge, Menu } from 'antd';
import React, { ReactElement } from 'react';
import { useSelector } from 'react-redux';
import { Link, useLocation } from 'react-router-dom';
import { backgroundProcessesSelectors } from '../../Services/ReduxStore/Reducers/BackgroundProcess';
import { store } from '../../Services/ReduxStore/Store';
 

export interface NavMenuProps {
  collapsed: boolean;
}


const { SubMenu } = Menu;
// submenu keys of first level
const rootSubmenuKeys = ['users', 'registry', 'security'];


export const NavMenu = ({
  collapsed
}: NavMenuProps): ReactElement => {
  const location = useLocation();
  const currentUser = store.getState().currentUser.user;
  const backgroundProcesses = useSelector(backgroundProcessesSelectors.selectAll);
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
        key ='notify:background-processes'
        icon={
          <Badge 
            count={backgroundProcesses.length}
            overflowCount={10}
            status='processing'           
          >
            <UnorderedListOutlined />
          </Badge>}
      >
        <Link to='/notify/background-processes'>Processes</Link>
      </Menu.Item>

      <Menu.Item
        key='logout'
        icon={<LogoutOutlined />}
      >
        <Link to='/logout'>Logout ({currentUser.attributes.username})</Link>
      </Menu.Item>
      
    </Menu>
  );
};
