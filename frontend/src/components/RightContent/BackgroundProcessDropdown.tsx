import { backgroundProcessesSelectors, fetchAll } from '@/services/ReduxStore/Reducers/BackgroundProcesses';
import { HourglassOutlined, PauseCircleTwoTone } from '@ant-design/icons';
import { Menu, Progress } from 'antd';
import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import HeaderDropdown from '../HeaderDropdown';
import styles from './index.less';

export type GlobalHeaderRightProps = {
  menu?: boolean;
};

const getStatus = (backgroundProcess: any): any => {
  switch (backgroundProcess.attributes?.status) {
      case 'running':
      case 'successed':
      case 'failed':
      return <Progress
          type='circle'
          percent={backgroundProcess.attributes?.progress}
          width={60}
          status={backgroundProcess.attributes?.status === 'failed' ? 'exception' : undefined} />;
      default:
      return <PauseCircleTwoTone
          twoToneColor='#f2f207'
          style={{ width: 60, fontSize: '2vw' }}/>;
  }
};

const BackgroundProcessDropdown: React.FC<GlobalHeaderRightProps> = ({ menu }) => {
  const dispatch = useDispatch();
  const entries = useSelector(backgroundProcessesSelectors.selectAll);
  const {loading, error, initialized} = useSelector((state: any) => state.backgroundProcesses);

  const [menuItems, setMenuItems] = useState<any[]>([]);

  useEffect(() => {
    if (entries.length === 0 && loading === 'idle' && !initialized){
      console.log('fetching');
  
      dispatch(fetchAll());
      } else {
        const menus = Object.entries(entries).map((key) => {
          return (
            <Menu.Item key={key[0]}>
              {getStatus(key[0])}
            </Menu.Item>
          )
        });
        setMenuItems(menus);
      }
    
  }, [dispatch, entries, error, initialized, loading]);

  

  const menuHeaderDropdown = (
    <Menu className={styles.menu} selectedKeys={[]}>
      {menuItems}
    </Menu>
  );

  return (
    <HeaderDropdown overlay={menuHeaderDropdown}>
        <HourglassOutlined />
    </HeaderDropdown>
  );
};

export default BackgroundProcessDropdown;
