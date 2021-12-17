import { Card, Progress } from 'antd';
import React, { useEffect, useState } from 'react';
import { useDispatch } from 'react-redux';

import { initialTaskResults } from '../../Features/TaskResult/taskResultSlice';
import { useAppSelector } from '../../Hooks/Store';

export const TaskProgressCard = (): JSX.Element => {
  const taskResults = useAppSelector((state) => state.taskResults.value);

  const [taskCards, setTaskCards] = useState<any>(); // TODO: any is not correct
  const dispatch = useDispatch();

  useEffect(() => {
    initialTaskResults(dispatch);
  }, []);

  useEffect(() => {
    const taskCards = Object.entries(taskResults).map(([key, value]) => {
      const taskResult = value.attributes;
      const status = taskResult.status === 'FAILURE' ? 'exception' : undefined;

      let percent = 0;
      if (Object.prototype.hasOwnProperty.call(taskResult.task_meta, 'total') &&
          Object.prototype.hasOwnProperty.call(taskResult.task_meta, 'done') &&
          taskResult.task_meta.total && taskResult.task_meta.done
      ) {
        percent = Math.round((taskResult.task_meta.done / taskResult.task_meta.total) * 100);
      } else if (taskResult.status === 'FAILURE' || taskResult.status === 'SUCCESS') {
        percent = 100;
      }

      let phase;
      if (Object.prototype.hasOwnProperty.call(taskResult.task_meta, 'phase') &&
      taskResult.task_meta.phase) {
        phase = taskResult.task_meta.phase;
      } else if (
        taskResult.result &&
        Object.prototype.hasOwnProperty.call(taskResult.result, 'links') && taskResult.result &&
        Object.prototype.hasOwnProperty.call(taskResult.result.links, 'self')) {
        phase = <a href={taskResult.result.links.self}></a>;
      }

      const msg = value.attributes.traceback ? value.attributes.traceback : phase;
      const title = value.attributes.task_name.includes('build_ogc_service') ? 'Register new OGC Service' : 'unknown';

      return (
        <Card key={key} title={title} bordered={false} style={{ width: 300 }}>
            <p>{msg}</p>
            <Progress type='circle' percent={percent} width={80} status={status} />
        </Card>);
    });
    setTaskCards(taskCards);
  }, [taskResults]);

  return (
    <div>
    {taskCards}
    </div>
  );
};
