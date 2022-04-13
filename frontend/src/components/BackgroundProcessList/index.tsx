
import { backgroundProcessesSelectors } from '@/services/ReduxStore/Reducers/BackgroundProcesses';
import { PauseCircleTwoTone } from '@ant-design/icons';
import { Menu, Progress } from 'antd';
import React, { useEffect } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useDispatch, useSelector } from 'react-redux';
import styles from './index.less';

export const ProgressList = (): JSX.Element => {
  const backgroundProcesses = useSelector(backgroundProcessesSelectors.selectAll);
  const [listBackgroundProcess, { response: listBackgroundProcessResponse }] = useOperationMethod('listBackgroundProcess');
  const dispatch = useDispatch();

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
      }
    
  }, [backgroundProcesses, listBackgroundProcess, listBackgroundProcessResponse]);



//   const getDescription = (taskResult: any): any => {
//     let message;
//     if (taskResult.attributes.status === 'PENDING') {
//       return 'Task is waiting for worker';
//     }
//     if (Object.prototype.hasOwnProperty.call(taskResult.attributes.result, 'phase') &&
//       taskResult.attributes.result.phase) {
//       message = taskResult.attributes.result.phase;
//     } else if (
//       taskResult.attributes.result && taskResult.attributes.result.data) {
//       const data = taskResult.attributes.result.data as any;
//       message = <a href={data.links?.self}>result</a>;
//     }

//     return taskResult.attributes.traceback ? taskResult.attributes.traceback : message;
//   };

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
  return (
    <Menu className={styles.menu} selectedKeys={[]}>
      <Menu.Item>
      <a target="_blank" rel="noopener noreferrer" href="https://www.antgroup.com">
        1st menu item
      </a>
    </Menu.Item>
    </Menu>
    // <List
    //   dataSource={backgroundProcesses}
    //   renderItem={item => (
    //     <List.Item key={item.id}>
    //       <List.Item.Meta
    //         avatar={getStatus(item)}
    //         title={item.attributes?.taskName?.includes('build_ogc_service')
    //           ? 'Register new OGC Service' + item.id
    //           : item.attributes?.taskName}
    //         description={'lalalala'}
    //       />
    //     </List.Item>
    //   )}
    // />
  );
};