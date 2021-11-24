import { Form, Input, Button, Checkbox } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { CSRFToken } from '../../CSRF/CSRF';
import { useAuth } from '../../../Hooks/AuthUserProvider';


export const LoginForm = () => {
  const [, handleAuth] = useAuth();

  const onFinish = (values: any) => {
    console.log('Received values of form: ', values);
    handleAuth({username: values.username, password: values.password}, "loginUser");
  };

  return (
    <Form
      name="normal_login"
      className="login-form"
      initialValues={{ remember: true }}
      onFinish={onFinish}
    >
      <CSRFToken />
      <Form.Item
        name="username"
        rules={[{ required: true, message: 'Please input your Username!' }]}
      >
        <Input prefix={<UserOutlined className="site-form-item-icon" />} placeholder="Username" />
      </Form.Item>
      <Form.Item
        name="password"
        rules={[{ required: true, message: 'Please input your Password!' }]}
      >
        <Input
          prefix={<LockOutlined className="site-form-item-icon" />}
          type="password"
          placeholder="Password"
        />
      </Form.Item>
      <Form.Item>
        <Form.Item name="remember" valuePropName="checked" noStyle>
          <Checkbox>Remember me</Checkbox>
        </Form.Item>

        <span className="login-form-forgot">
          Forgot password
        </span>
      </Form.Item>

      <Form.Item>
        <Button type="primary" htmlType="submit" className="login-form-button">
          Log in
        </Button>
        Or <span>register now!</span>
      </Form.Item>
    </Form>
  );
};
