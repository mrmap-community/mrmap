import { Progress } from 'antd';
import React from 'react';
import RepoTable from '../Shared/RepoTable/NewRepoTable';


const BackgroundProcessTable = (): JSX.Element => {
  
  const getStatus = (backgroundProcess: any): any => {
    switch (backgroundProcess.status) {
    case 'running':
      return 'active';
    case 'successed':
      return 'success';
    case 'failed':
      return 'exception';
    case 'unknown':
    case 'pending':
    default:
      return 'normal';
    }
  };


  return <RepoTable
    resourceTypes={['BackgroundProcess']}
    columns={
      [{
        dataIndex: 'progress',
        renderText: (text, record, index, action)=>{
          return <Progress
            percent={Math.round(text)}
            status={getStatus(record)} 
          />;
        }
        
      }]
    }
  />;
};

export default BackgroundProcessTable;
