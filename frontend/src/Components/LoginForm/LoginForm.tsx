import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Form, Input, notification, Row } from 'antd';
import React, { ReactElement, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../Hooks/useAuth';

export const Login = (): ReactElement => {
  const auth = useAuth();
  const navigate = useNavigate();
  // workaround for a strange issue with TypeScript version 4.4.4
  // (currently cannot update to 4.5.4 due to eslint incompatibility)
  const location: any = useLocation();
  const [loggingIn, setLoggingIn] = useState(false);
  const [loginFailed, setLoginFailed] = useState(false);

  const from = location.state?.from?.pathname || '/';

  const onFinish = (values: any) => {
    async function login (username: string, password: string) {
      if (!auth) return;
      setLoggingIn(true);
      const success = await auth.login(username, password);
      setLoggingIn(false);
      if (!success) {
        notification.error({
          message: 'Failed to log in.'
        });
        setLoginFailed(true);
      } else {
        notification.success({
          message: 'Successfully logged in.'
        });
        setLoginFailed(false);
        navigate(from, { replace: true });
      }
    }
    login(values.username, values.password);
  };

  return (
    <Row justify='center' align='middle' style={{ minHeight: '100vh', backgroundColor: '#001529' }}>
      <Form
        name='normal_login'
        initialValues={{ remember: true }}
        onFinish={onFinish}
      >
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
        {loginFailed
          ? (
            <Form.Item><Alert message='Login failed. Hint: mrmap/mrmap' type='error' showIcon /></Form.Item>
          )
          : (<></>)
        }
        <Form.Item>
          <Button size='large' type='primary' loading={loggingIn}
            htmlType='submit'>
            {loggingIn ? 'Logging in' : 'Log in'}
          </Button>
        </Form.Item>
      </Form>
    </Row>
  );
};
