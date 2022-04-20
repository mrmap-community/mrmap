import SchemaTable from '@/components/SchemaTable';
import { LockFilled, UnlockFilled } from '@ant-design/icons';
import { PageContainer } from '@ant-design/pro-layout';
import { Button, Tooltip } from 'antd';
import type { ReactElement } from 'react';
import React, { useCallback } from 'react';
import { Link } from 'umi';

const WfsTable = (): ReactElement => {
  const additionalActions = useCallback((text: any, record: any): React.ReactNode => {
    const allowedOperations = record.relationships?.allowedOperations?.meta?.count;
    return (
      <Tooltip
        title={
          allowedOperations > 0 ? `Zugriffsregeln: ${allowedOperations}` : 'Zugriff unbeschränkt'
        }
      >
        <Link to={`/registry/services/wfs/${record.id}/security`}>
          <Button
            size="small"
            style={{ borderColor: 'gold', color: 'gold' }}
            icon={allowedOperations > 0 ? <LockFilled /> : <UnlockFilled />}
          />
        </Link>
      </Tooltip>
    );
  }, []);
  return (
    <PageContainer>
      <SchemaTable resourceTypes={['WebFeatureService']} additionalActions={additionalActions} />
    </PageContainer>
  );
};

export default WfsTable;