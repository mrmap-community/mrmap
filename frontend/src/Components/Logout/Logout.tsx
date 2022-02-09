import React, { ReactElement, useEffect } from 'react';

import { notification, Row, Spin } from 'antd';
import { useNavigate } from 'react-router';

import { useAuth } from '../../Hooks/useAuth';


export const Logout = (): ReactElement => {
  const auth = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    async function ensureLogoutAndForwardToLogin () {
      if (auth && auth.user) {
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
  }, [auth, navigate]);

  return (
    <Row justify='center' align='middle' style={{ minHeight: '100vh', backgroundColor: '#001529' }}>
      {auth && auth.user && <Spin tip={`Logging out "${auth.user.name}"...`} />}
    </Row>
  );
};
