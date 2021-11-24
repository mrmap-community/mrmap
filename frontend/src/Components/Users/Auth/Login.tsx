import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Form, Input, Row } from 'antd';
import React, { ReactElement } from 'react';

import { useAuth } from '../../../Hooks/AuthUserProvider';
import { CSRFToken } from '../../CSRF/CSRF';

export const LoginForm = (): ReactElement => {
  // @ts-ignore
  const [, handleAuth] = useAuth();
  const [form] = Form.useForm();

  const onFinish = (values: any) => {
    // eslint-disable-next-line
    console.log('Received values of form: ', values);
    handleAuth({ username: values.username, password: values.password }, 'loginUser');
  };

  return (
    <Row justify="center" align="middle" style={{ minHeight: '100vh', backgroundColor: '#001529' }}>
      <Form
        name='normal_login'
        initialValues={{ remember: true }}
        onFinish={onFinish}
      >
        <CSRFToken />
        <Form.Item
          name='username'
          rules={[{ required: true, message: 'Please input your Username!' }]}
        >
          <Input size='large' prefix={<UserOutlined />}
            placeholder='Username' />
        </Form.Item>
        <Form.Item
          name='password'
          rules={[{ required: true, message: 'Please input your Password!' }]}
        >
          <Input
            size='large'
            prefix={<LockOutlined />}
            type='password'
            placeholder='Password'
          />
        </Form.Item>
        <Form.Item>
          <Button size='large' type='primary'
            htmlType='submit'>
            Log in
          </Button>
        </Form.Item>
      </Form>
    </Row>
  );
};
