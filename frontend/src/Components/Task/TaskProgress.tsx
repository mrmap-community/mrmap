import { PauseCircleTwoTone } from '@ant-design/icons';
import { List, Progress } from 'antd';
import React, { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { JsonApiPrimaryData } from '../../Repos/JsonApiRepo';
import { TaskResult } from '../../Repos/TaskResultRepo';
import { fetchTaskResults, taskResultsSelectors } from '../../Services/ReduxStore/Reducers/TaskResult';

// TODO: Rename to TaskProgressList
export const TaskProgressList = (): JSX.Element => {
  const taskResults = useSelector(taskResultsSelectors.selectAll);

  const dispatch = useDispatch();

  useEffect(() => {
    dispatch(fetchTaskResults());
  }, [dispatch]);

  const calculatePercent = (taskResult: TaskResult): number => {
    let percent = 0;
    if (Object.prototype.hasOwnProperty.call(taskResult.attributes.result, 'total') &&
          Object.prototype.hasOwnProperty.call(taskResult.attributes.result, 'done') &&
          taskResult.attributes.result.total && taskResult.attributes.result.done
    ) {
      percent = Math.round((taskResult.attributes.result.done / taskResult.attributes.result.total) * 100);
    } else if (taskResult.attributes.status === 'FAILURE' || taskResult.attributes.status === 'SUCCESS') {
      percent = 100;
    }
    return percent;
  };

  const getDescription = (taskResult: TaskResult): any => {
    let message;
    if (taskResult.attributes.status === 'PENDING') {
      return 'Task is waiting for worker';
    }
    if (Object.prototype.hasOwnProperty.call(taskResult.attributes.result, 'phase') &&
      taskResult.attributes.result.phase) {
      message = taskResult.attributes.result.phase;
    } else if (
      taskResult.attributes.result && taskResult.attributes.result.data) {
      const data = taskResult.attributes.result.data as JsonApiPrimaryData;
      message = <a href={data.links?.self}>result</a>;
    }

    return taskResult.attributes.traceback ? taskResult.attributes.traceback : message;
  };

  const getStatus = (taskResult: TaskResult): any => {
    switch (taskResult.attributes.status) {
    case 'STARTED':
    case 'SUCCESS':
    case 'FAILURE':
      return <Progress
        type='circle'
        percent={calculatePercent(taskResult)}
        width={60}
        status={taskResult.attributes.status === 'FAILURE' ? 'exception' : undefined} />;
    default:
      return <PauseCircleTwoTone
        twoToneColor='#f2f207'
        style={{ width: 60, fontSize: '2vw' }}/>;
    }
  };
  return (

    <List
      dataSource={taskResults}
      renderItem={item => (
        <List.Item key={item.id}>
          <List.Item.Meta
            avatar={getStatus(item)}
            title={item.attributes.task_name?.includes('build_ogc_service')
              ? 'Register new OGC Service' + item.id
              : item.attributes.task_name}
            description={getDescription(item)}
          />
        </List.Item>
      )}
    />
  );
};
