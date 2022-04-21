import SchemaTable from '@/components/SchemaTable';
import { CloudDownloadOutlined } from '@ant-design/icons';
import { PageContainer } from '@ant-design/pro-layout';
import { Button, Tooltip } from 'antd';
import type { ReactElement } from 'react';
import React, { useCallback } from 'react';
import { Link, useIntl } from 'umi';

const CswTable = (): ReactElement => {
  const intl = useIntl();
  const additionalActions = useCallback(
    (text: any, record: any): React.ReactNode => {
      return (
        <Tooltip title={intl.formatMessage({ id: 'pages.cswTable.runHarvesting' })}>
          <Link to={`/registry/services/csw/${record.id}/TODO`}>
            <Button
              size="small"
              style={{ borderColor: 'blue', color: 'blue' }}
              icon={<CloudDownloadOutlined />}
            />
          </Link>
        </Tooltip>
      );
    },
    [intl],
  );
  return (
    <PageContainer>
      <SchemaTable resourceTypes={['CatalougeService']} additionalActions={additionalActions} />
    </PageContainer>
  );
};

export default CswTable;
