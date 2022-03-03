import { CloudDownloadOutlined } from '@ant-design/icons';
import { Button, Tooltip } from 'antd';
import React, { useCallback } from 'react';
import RepoTable from '../Shared/RepoTable/NewRepoTable';


const CswTable = (): JSX.Element => {

  const additionalActions = useCallback((text: any, record:any): React.ReactNode => {
    return (
      <Tooltip 
        title={ 'run harvesting' }>
        <Button
          size='small'
          style={{ borderColor: 'blue', color: 'blue' }}
          icon={<CloudDownloadOutlined />}
          //onClick={ } //TODO
        >
        </Button>
      </Tooltip>
    );
  },[],
  );

  return <RepoTable
    resourceTypes={['CatalougeService']}
    additionalActions={additionalActions}
  />;
};

export default CswTable;
