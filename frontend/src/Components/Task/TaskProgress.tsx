import { Card, Progress } from 'antd';
import React, { useEffect, useState } from 'react';

import { useAppSelector } from '../../Hooks/Store';

export const TaskProgressCard = (): JSX.Element => {
  const taskResults = useAppSelector((state) => state.taskResults.value);

  const [taskCards, setTaskCards] = useState<any>(); // TODO: any is not correct

  useEffect(() => {
    const taskCards = Object.entries(taskResults).map(([key, value]) => {
      const status = value.attributes.status === 'FAILURE' ? 'exception' : undefined;

      let percent = 0;
      if (value.attributes.task_meta.hasOwnProperty('total') && value.attributes.task_meta.hasOwnProperty('done') &&
        value.attributes.task_meta.total && value.attributes.task_meta.done
      ) {
        percent = Math.round((value.attributes.task_meta.done / value.attributes.task_meta.total) * 100);
      }

      let phase = '';
      if (value.attributes.task_meta.hasOwnProperty('phase') && value.attributes.task_meta.phase) {
        phase = value.attributes.task_meta.phase;
      }
      const msg = value.attributes.traceback ? value.attributes.traceback : phase;

      return (
        <Card key={key} title={value.id} bordered={false} style={{ width: 300 }}>
            <p>{msg}</p>
            <Progress type='circle' percent={percent} width={80} status={status} />
        </Card>);
    });
    setTaskCards(taskCards);
  }, [taskResults]);

  return (
    <div>
      test
    {taskCards}
    </div>
  );
};
