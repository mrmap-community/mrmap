import SchemaTable from '@/components/SchemaTable';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  SmallDashOutlined,
  SyncOutlined,
} from '@ant-design/icons';
import { PageContainer } from '@ant-design/pro-layout';
import { Tag } from 'antd';
import React from 'react';

const BackgroundProcessesTable = (): React.ReactElement => {
  return (
    <PageContainer>
      <SchemaTable
        resourceTypes={{ baseResourceType: 'BackgroundProcess' }}
        columns={[
          {
            dataIndex: 'progress',
            valueType: (item: any) => ({
              type: 'progress',
              status:
                item.status === 'successed'
                  ? 'success'
                  : item.status === 'failed'
                  ? 'exception'
                  : 'active',
            }),
          },
          {
            dataIndex: 'status',
            render: (entity: any) => {
              switch (entity) {
                case 'running':
                  return (
                    <Tag icon={<SyncOutlined spin />} color="processing">
                      processing
                    </Tag>
                  );
                case 'failed':
                  return (
                    <Tag icon={<CloseCircleOutlined />} color="error">
                      error
                    </Tag>
                  );
                case 'pending':
                  return (
                    <Tag icon={<SmallDashOutlined />} color="warning">
                      pending
                    </Tag>
                  );
                case 'successed':
                  return (
                    <Tag icon={<CheckCircleOutlined />} color="success">
                      successed
                    </Tag>
                  );
                case 'unknown':
                default:
                  return (
                    <Tag icon={<QuestionCircleOutlined />} color="default">
                      unknown
                    </Tag>
                  );
              }
            },
          },
        ]}
      />
    </PageContainer>
  );
};

export default BackgroundProcessesTable;
