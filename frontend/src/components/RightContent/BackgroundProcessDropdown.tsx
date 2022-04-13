import { backgroundProcessesSelectors } from '@/services/ReduxStore/Reducers/BackgroundProcesses';
import { HourglassOutlined, PauseCircleTwoTone } from '@ant-design/icons';
import { Menu, Progress } from 'antd';
import React, { useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
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
  
  const backgroundProcesses = useSelector(backgroundProcessesSelectors.selectAll);
  const [listBackgroundProcess, { response: listBackgroundProcessResponse }] = useOperationMethod('listBackgroundProcess');
  const dispatch = useDispatch();
  const [menuItems, setMenuItems] = useState<any[]>([]);

  useEffect(() => {
    if (listBackgroundProcessResponse){
        dispatch({
            type: 'backgroundProcesses/set', 
            payload: listBackgroundProcessResponse.data.data
        });
    }
  }, [dispatch, listBackgroundProcessResponse]);

  useEffect(() => {
      if (backgroundProcesses.length === 0 && !listBackgroundProcessResponse){
        listBackgroundProcess();
        console.log('not initialized - fetching data...', backgroundProcesses);
      } else {
        console.log('data', backgroundProcesses)
        const menus = Object.entries(backgroundProcesses).map((key) => {
          return (
            <Menu.Item key={key[0]}>
              {getStatus(key[0])}
            </Menu.Item>
          )
        });
        setMenuItems(menus);
      }
    
  }, [backgroundProcesses, listBackgroundProcess, listBackgroundProcessResponse]);

  

  

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
