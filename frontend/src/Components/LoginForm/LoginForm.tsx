import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Form, Image, Input, Row } from 'antd';
import { RequestPayload } from 'openapi-client-axios';
import React, { ReactElement, useEffect } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../Hooks/useAuth';


export const Login = (): ReactElement => {
  const auth = useAuth();
  const navigate = useNavigate();
  // workaround for a strange issue with TypeScript version 4.4.4
  // (currently cannot update to 4.5.4 due to eslint incompatibility)
  const location: any = useLocation();
  const [createLoginRequest, { loading: loginLoading, error: loginError, data: loginData }] = useOperationMethod('addLoginRequest');
  const [getCurrentUser, { loading: userLoading, error: userError, data: userData }] = useOperationMethod('getCurrentUser');

  //const [loggingIn, setLoggingIn] = useState(false);
  //const [loginFailed, setLoginFailed] = useState(false);

  useEffect(() => {
    // TODO: set currentUser
    // const from = location.state?.from?.pathname || '/';
    // navigate(from);
    console.log(userData);
    auth?.setUser(userData);
  }, [userData, auth]);


  useEffect(() => {
    getCurrentUser();
  }, [getCurrentUser, loginData]);

  const onFinish = (values: any) => {
    const jsonApiPayload: RequestPayload = {
      'data': {
        'type': 'LoginRequest',
        'attributes': values
      }
    };
    createLoginRequest(undefined, jsonApiPayload);
  };

  return (
    <Row justify='center' align='middle' style={{ minHeight: '100vh', backgroundColor: '#001529' }}>
      
      <Form
        name='normal_login'
        initialValues={{ remember: true }}
        onFinish={onFinish}
      >
        <Image
          width={200}
          alt={'Mr. Map logo'}
          src={process.env.PUBLIC_URL + '/logo.png'}
        />
        <Form.Item
          name='username'
          rules={[{ required: true, message: 'Please enter your Username!' }]}
        >
          <Input size='large' prefix={<UserOutlined />}
            placeholder='Username' />
        </Form.Item>
        <Form.Item
          name='password'
          rules={[{ required: true, message: 'Please enter your Password!' }]}
        >
          <Input
            size='large'
            prefix={<LockOutlined />}
            type='password'
            placeholder='Password'
          />
        </Form.Item>
        {loginError || userError
          ? (
            <Form.Item><Alert message='Login failed. Hint: mrmap/mrmap' type='error' showIcon /></Form.Item>
          )
          : (<></>)
        }
        <Form.Item>
          <Button size='large' type='primary' loading={loginLoading || userLoading}
            htmlType='submit'>
            {loginLoading || userLoading ? 'Logging in' : 'Log in'}
          </Button>
        </Form.Item>
      </Form>
      
    </Row>
  );
};
