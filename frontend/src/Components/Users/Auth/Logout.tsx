import { notification, Row, Spin } from 'antd';
import React, { ReactElement, useEffect } from 'react';
import { useNavigate } from 'react-router';

import { useAuth } from '../../../Hooks/AuthContextProvider';

export const Logout = (): ReactElement => {
  const auth = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    async function ensureLogoutAndForwardToLogin () {
      if (auth.user) {
        if (await auth.logout()) {
          notification.success({
            message: 'Successfully logged out.'
          });
        } else {
          notification.error({
            message: 'Logout failed.'
          });
        }
      }
      navigate('/login');
    }
    ensureLogoutAndForwardToLogin();
  }, [auth]);

  return (
    <Row justify='center' align='middle' style={{ minHeight: '100vh', backgroundColor: '#001529' }}>
      {auth.user && <Spin tip={`Logging out "${auth.user.name}"...`} />}
    </Row>
  );
};
