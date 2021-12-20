import { List, Progress } from 'antd';
import React, { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { fetchTaskResults, taskResultsSelectors } from '../../Features/TaskResult/taskResultSlice';
import { JsonApiPrimaryData } from '../../Repos/JsonApiRepo';
import { TaskResult } from '../../Repos/TaskResultRepo';

// TODO: Rename to TaskProgressList
export const TaskProgressList = (): JSX.Element => {
  const taskResults = useSelector(taskResultsSelectors.selectAll)

  const dispatch = useDispatch();

  useEffect(() => {
    dispatch(fetchTaskResults());
  }, [dispatch]);

  const calculatePercent = (taskResult: TaskResult): number => {
    let percent = 0;
    if (Object.prototype.hasOwnProperty.call(taskResult.attributes.task_meta, 'total') &&
          Object.prototype.hasOwnProperty.call(taskResult.attributes.task_meta, 'done') &&
          taskResult.attributes.task_meta.total && taskResult.attributes.task_meta.done
    ) {
      percent = Math.round((taskResult.attributes.task_meta.done / taskResult.attributes.task_meta.total) * 100);
    } else if (taskResult.attributes.status === 'FAILURE' || taskResult.attributes.status === 'SUCCESS') {
      percent = 100;
    }
    return percent;
  };

  const getDescription = (taskResult: TaskResult): any => {
    let message;
    if (Object.prototype.hasOwnProperty.call(taskResult.attributes.task_meta, 'phase') &&
      taskResult.attributes.task_meta.phase) {
      message = taskResult.attributes.task_meta.phase;
    } else if (
      taskResult.attributes.result && taskResult.attributes.result.data) {
      const data = taskResult.attributes.result.data as JsonApiPrimaryData;
      message = <a href={data.links?.self}>result</a>;
    }

    return taskResult.attributes.traceback ? taskResult.attributes.traceback : message;
  };

  return (

        <List
          dataSource={taskResults}
          renderItem={item => (
            <List.Item key={item.id}>
              <List.Item.Meta
                avatar={<Progress
                  type='circle'
                  percent={calculatePercent(item)}
                  width={60}
                  status={item.attributes.status === 'FAILURE' ? 'exception' : undefined} />}
                title={item.attributes.task_name?.includes('build_ogc_service')
                  ? 'Register new OGC Service'
                  : item.attributes.task_name}
                description={getDescription(item)}
              />
            </List.Item>
          )}
        />
  );
};
