import { LockFilled, UnlockFilled } from '@ant-design/icons';
import { Button, Tooltip } from 'antd';
import React, { useCallback } from 'react';
import { useNavigate } from 'react-router';
import RepoTable from '../Shared/RepoTable/NewRepoTable';


const WmsTable = (): JSX.Element => {
  const navigate = useNavigate();
  const additionalActions = useCallback((text: any, record:any): React.ReactNode => {
    const allowedOperations = record.relationships?.allowedOperations?.meta?.count;
    return (
      <Tooltip 
        title={ allowedOperations > 0 ? `Zugriffsregeln: ${allowedOperations}` : 'Zugriff unbeschränkt' }>
        <Button
          size='small'
          style={{ borderColor: 'gold', color: 'gold' }}
          icon={allowedOperations > 0 ? <LockFilled/> : <UnlockFilled/>}
          onClick={ () => {
            navigate(`/registry/services/wms/${record.id}/security`);
          }}
        >
        </Button>
      </Tooltip>
    );
  },[navigate],
  );

  return <RepoTable
    resourceTypes={['WebMapService']}
    additionalActions={additionalActions}
  />;
};

export default WmsTable;
