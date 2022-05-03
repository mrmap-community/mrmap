import SchemaTable from '@/components/SchemaTable';
import { InfoCircleOutlined, LockFilled, UnlockFilled } from '@ant-design/icons';
import { PageContainer } from '@ant-design/pro-layout';
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
          title='show details'
        >
          <Link
           to={`/registry/wms/${record.id}/details`}>
             <Button
              size='small'
              icon={<InfoCircleOutlined />}
             
             />
          </Link>
        </Tooltip>
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
    <PageContainer>
      <SchemaTable resourceTypes={['WebMapService']} additionalActions={additionalActions} />
    </PageContainer>
  );
};

export default WmsTable;
