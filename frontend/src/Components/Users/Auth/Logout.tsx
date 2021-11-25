import { Row, Spin } from 'antd';
import React, { ReactElement, useEffect } from 'react';
import { useAuth } from '../../../Hooks/AuthContextProvider';

export const Logout = (): ReactElement => {
  const auth = useAuth();

  useEffect(() => {
    auth.logout();
  }, [auth]);

  return (
    <Row justify="center" align="middle" style={{ minHeight: '100vh', backgroundColor: '#001529' }}>
      <Spin tip={`Logging out "${auth.user}"...`} />
    </Row>
  );
};
