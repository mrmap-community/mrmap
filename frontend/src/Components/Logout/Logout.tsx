import { Row, Spin } from 'antd';
import React, { ReactElement, useEffect } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useDispatch } from 'react-redux';
import { useNavigate } from 'react-router';
import { store } from '../../Services/ReduxStore/Store';

export const Logout = (): ReactElement => {
  const navigate = useNavigate();
  const [deleteLogoutRequest, { response: logoutResponse }] = useOperationMethod('deleteLogout');
  const currentUser = store.getState().currentUser.user;
  const dispatch = useDispatch();
  
  useEffect(() => {
    deleteLogoutRequest();
  }, [deleteLogoutRequest]);

  useEffect(() => {
    if (logoutResponse && logoutResponse.status === 200) {
      dispatch({
        type: 'currentUser/clear'
      });
      navigate('/login');  
    }
  }, [navigate, logoutResponse, dispatch]);

  return (
    <Row justify='center' align='middle' style={{ minHeight: '100vh', backgroundColor: '#001529' }}>
      {currentUser  && <Spin tip={`Logging out "${currentUser?.attributes?.username}"...`} />}
    </Row>
    

  );
};
