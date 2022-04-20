import Footer from '@/components/Footer';
import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { LoginForm, ProFormCheckbox, ProFormText } from '@ant-design/pro-form';
import { Alert, message } from 'antd';
import type { RequestPayload } from 'openapi-client-axios';
import type { ReactElement } from 'react';
import React, { useCallback, useEffect } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { FormattedMessage, history, SelectLang, useIntl, useModel } from 'umi';
import styles from './index.less';

const LoginMessage: React.FC<{
  content: string;
}> = ({ content }) => (
  <Alert
    style={{
      marginBottom: 24,
    }}
    message={content}
    type="error"
    showIcon
  />
);

const Login: React.FC = (): ReactElement => {
  const intl = useIntl();
  const { setInitialState } = useModel('@@initialState');

  const [
    createLoginRequest,
    { error: loginError, response: loginResponse },
  ] = useOperationMethod('addLoginRequest');
  const [
    getCurrentUser,
    {error: currentUserError, response: currentUserResponse}
  ] = useOperationMethod('getCurrentUser');
  
  /**
   * @description handles successfully login process; redirects to the last page
   */
  useEffect(()=> {
    if(currentUserResponse && currentUserResponse.status === 200){
      const defaultLoginSuccessMessage = intl.formatMessage({
        id: 'pages.login.success',
        defaultMessage: 'Login succesful！',
      });
      message.success(defaultLoginSuccessMessage);
      setInitialState((s: any) => ({
        ...s,
        currentUser: currentUserResponse.data
      }));
      
      if (history) {
        /** Redirect to the page specified by redirect parameter */
        const { query } = history.location;
        const { redirect } = query as { redirect: string };
        setTimeout(() => {
          history.push(redirect || '/');
        });
      }
    }
  }, [currentUserResponse, intl, setInitialState]);

  /**
   * @description triggers get current user request if login was successfully
   */
  useEffect(()=> {
    if (loginResponse && loginResponse.status === 200){
      getCurrentUser();
    }
  }, [getCurrentUser, intl, loginResponse]);

  /**
   * @description handles errors on login processing
   */
  useEffect(() => {
    if (loginError || currentUserError){
      const defaultLoginFailureMessage = intl.formatMessage({
        id: 'pages.login.failure',
        defaultMessage: 'Login failed, please try again!',
      });
      message.error(defaultLoginFailureMessage);
    }
  }, [intl, loginError, currentUserError]);
  
  /**
   * @description callback function to start login processing
   */
  const onFinish = useCallback((values: any) => {
    const jsonApiPayload: RequestPayload = {
      data: {
        type: 'LoginRequest',
        attributes: {
          username: values.username,
          password: values.password
        },
      },
    };
    createLoginRequest(undefined, jsonApiPayload);
  },
  [createLoginRequest]
  );

  return (
    <div className={styles.container}>
      <div className={styles.lang} data-lang>
        {SelectLang && <SelectLang />}
      </div>
      <div className={styles.content}>
        <LoginForm
          logo={<img alt="mr. map logo" src="/logo.png" />}
          //title="Mr. Map"
          subTitle={intl.formatMessage({ id: 'pages.layouts.userLayout.title' })}
          initialValues={{
            autoLogin: true,
          }}
          onFinish={async (values) => {
            onFinish(values);
          }}
        >
          {loginError && (
            <LoginMessage
              content={intl.formatMessage({
                id: 'pages.login.accountLogin.errorMessage',
                defaultMessage: '账户或密码错误(admin/ant.design)',
              })}
            />
          )}

          <ProFormText
            name="username"
            fieldProps={{
              size: 'large',
              prefix: <UserOutlined className={styles.prefixIcon} />,
            }}
            placeholder={intl.formatMessage({
              id: 'pages.login.username.placeholder',
              defaultMessage: '用户名: admin or user',
            })}
            rules={[
              {
                required: true,
                message: (
                  <FormattedMessage
                    id="pages.login.username.required"
                    defaultMessage="请输入用户名!"
                  />
                ),
              },
            ]}
          />
          <ProFormText.Password
            name="password"
            fieldProps={{
              size: 'large',
              prefix: <LockOutlined className={styles.prefixIcon} />,
            }}
            placeholder={intl.formatMessage({
              id: 'pages.login.password.placeholder',
              defaultMessage: '密码: ant.design',
            })}
            rules={[
              {
                required: true,
                message: (
                  <FormattedMessage
                    id="pages.login.password.required"
                    defaultMessage="请输入密码！"
                  />
                ),
              },
            ]}
          />

          <div
            style={{
              marginBottom: 24,
            }}
          >
            <ProFormCheckbox noStyle name="autoLogin">
              <FormattedMessage id="pages.login.rememberMe" defaultMessage="自动登录" />
            </ProFormCheckbox>
            <a
              style={{
                float: 'right',
              }}
            >
              <FormattedMessage id="pages.login.forgotPassword" defaultMessage="忘记密码" />
            </a>
          </div>
        </LoginForm>
      </div>
      <Footer />
    </div>
  );
};

export default Login;