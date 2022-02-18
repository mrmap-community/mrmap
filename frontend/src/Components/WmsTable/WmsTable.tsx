import { LockFilled, UnlockFilled } from '@ant-design/icons';
import { Button, Tooltip } from 'antd';
import React, { useRef } from 'react';
import { useNavigate } from 'react-router';
import RepoTable, { RepoActionType } from '../Shared/RepoTable/NewRepoTable';


const WmsTable = (): JSX.Element => {
  const actionRef = useRef<RepoActionType>();
  const navigate = useNavigate();
  const additionalActions = (text: any, record:any): React.ReactNode => {
    return (
      <Tooltip 
        title={ record.allowedOperations > 0 ? `Zugriffsregeln: ${record.allowedOperations}` : 'Zugriff unbeschränkt' }>
        <Button
          size='small'
          style={{ borderColor: 'gold', color: 'gold' }}
          icon={record.allowedOperations > 0 ? <LockFilled/> : <UnlockFilled/>}
          onClick={ () => {
            navigate(`/registry/services/wms/${record.id}/security`);
          }}
        >
        </Button>
      </Tooltip>
    );
  };

  return <RepoTable
    resourceType='WebMapService'
    additionalActions={additionalActions}
    actionRef={actionRef as any}
    onAddRecord='/registry/services/wms/add'
  />;
};

export default WmsTable;
