import { Button, Result } from 'antd';
import React from 'react';
import { FormattedMessage, history, useIntl } from 'umi';

const NoFoundPage: React.FC = () => {
  const intl = useIntl();
  return (
    <Result
      status="404"
      title="404"
      subTitle={intl.formatMessage({ id: 'pages.404.subtitle' })}
      extra={
        <Button type="primary" onClick={() => history.push('/')}>
          <FormattedMessage id="pages.404.backHome" />
        </Button>
      }
    />
  );
};

export default NoFoundPage;
