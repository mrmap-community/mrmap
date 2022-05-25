import GenericPageContainer from '@/components/PageContainer';
import SchemaTable from '@/components/SchemaTable';
import { LockFilled, UnlockFilled } from '@ant-design/icons';
import { Button, Tooltip } from 'antd';
import type { ReactElement } from 'react';
import React, { useCallback } from 'react';
import { Link, useIntl } from 'umi';

const WmsTable = (): ReactElement => {
  const intl = useIntl();
  const additionalActions = useCallback(
    (text: any, record: any): React.ReactNode => {
      const allowedOperations = record.relationships?.allowedOperations?.meta?.count;
      return (
        <>
        <Tooltip
          title={
            allowedOperations > 0
              ? intl.formatMessage(
                  { id: 'pages.wmsTable.securityRuleCount' },
                  { num: allowedOperations },
                )
              : intl.formatMessage({ id: 'pages.wmsTable.noSecurityRules' })
          }
        >
          <Link to={`/registry/wms/${record.id}/security/rules`}>
            <Button
              size="small"
              style={{ borderColor: 'gold', color: 'gold' }}
              icon={allowedOperations > 0 ? <LockFilled /> : <UnlockFilled />}
            />
          </Link>
        </Tooltip>
        </>
      );
    },
    [intl],
  );
  return (
    <GenericPageContainer>
      <SchemaTable 
        resourceTypes={{baseResourceType: 'WebMapService'}} 
        additionalActions={additionalActions} 
        detailsLink={(row) => {return `/registry/wms/${row.id}`}}
      />
    </GenericPageContainer>
  );
};

export default WmsTable;
