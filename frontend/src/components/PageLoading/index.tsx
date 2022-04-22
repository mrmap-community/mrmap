import { Spin } from 'antd';
import Title from 'antd/lib/typography/Title';
import type { ReactElement } from 'react';

type PageLoadingProps = {
  title?: string;
  titleLevel?: 5 | 4 | 3 | 2 | 1 | undefined;
  logo?: ReactElement;
};

const PageLoading = ({ title, titleLevel = 5, logo }: PageLoadingProps): ReactElement => {
  return (
    <div style={{ paddingTop: 100, textAlign: 'center' }}>
      <Title level={titleLevel}>{title}</Title>
      <Spin size="large">{logo}</Spin>
    </div>
  );
};

export default PageLoading;
