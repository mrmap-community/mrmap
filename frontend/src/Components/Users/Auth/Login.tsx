import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Alert, Button, Form, Input, Row } from 'antd';
import React, { ReactElement, useState } from 'react';
import { useNavigate } from 'react-router';
import { useAuth } from '../../../Hooks/AuthContextProvider';

export const Login = (): ReactElement => {
  const auth = useAuth();
  const navigate = useNavigate();
  const [loggingIn, setLoggingIn] = useState(false);
  const [loginFailed, setLoginFailed] = useState(false);

  const onFinish = (values: any) => {
    async function login(username: string, password: string) {
      setLoggingIn(true);
      const success = await auth.login(username, password);
      setLoggingIn(false);
      if (!success) {
        setLoginFailed(true);
        return;
      } else {
        setLoginFailed(false);
        navigate('/');
      }
    }
    login(values.username, values.password);
  };

  return (
    <Row justify="center" align="middle" style={{ minHeight: '100vh', backgroundColor: '#001529' }}>
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
        {loginFailed ? (
          <Form.Item><Alert message="Login failed. Hint: mrmap/mrmap" type="error" showIcon /></Form.Item>
        ) : (<></>)
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
