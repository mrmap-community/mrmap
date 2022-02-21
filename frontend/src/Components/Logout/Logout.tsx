import { Row, Spin } from 'antd';
import React, { ReactElement, useEffect } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router';
import { currentUserSelectors } from '../../Services/ReduxStore/Reducers/CurrentUser';

export const Logout = (): ReactElement => {
  const navigate = useNavigate();
  const [deleteLogoutRequest, { response: logoutResponse }] = useOperationMethod('deleteLogout');
  const currentUser = useSelector(currentUserSelectors.selectAll);
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
      {currentUser && currentUser[0] && <Spin tip={`Logging out "${currentUser[0]?.attributes.username}"...`} />}
    </Row>
    

  );
};
