import Footer from '@/components/Footer';
import {
  LockOutlined, UserOutlined
} from '@ant-design/icons';
import { LoginForm, ProFormCheckbox, ProFormText } from '@ant-design/pro-form';
import { Alert } from 'antd';
import type { RequestPayload } from 'openapi-client-axios';
import type { ReactElement } from 'react';
import React, { useEffect, useState } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { FormattedMessage, SelectLang, useIntl, useModel } from 'umi';
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
  const [userLoginState, setUserLoginState] = useState<API.LoginResult>({});

  const { initialState, setInitialState } = useModel('@@initialState');
  
  const [createLoginRequest, { loading: loginLoading, error: loginError, response: loginResponse  }] = useOperationMethod('addLoginRequest');
  const [getCurrentUser, { loading: userLoading, data: userData }] = useOperationMethod('getCurrentUser');

  const intl = useIntl();

  const fetchUserInfo = async () => {
    const userInfo = await initialState?.fetchUserInfo?.();
    if (userInfo) {
      await setInitialState((s) => ({
        ...s,
        currentUser: userInfo,
      }));
    }
  };

  const onFinish = async (values: API.LoginParams) => {
    const jsonApiPayload: RequestPayload = {
      'data': {
        'type': 'LoginRequest',
        'attributes': values
      }
    };
    try {
      await createLoginRequest(undefined, jsonApiPayload);

    } catch (error) {
      console.log(error);
      console.log(loginError);
      console.log(loginLoading);
      console.log(loginResponse);
    }
  };

  useEffect(() => {
    if (loginResponse && loginResponse.status === 200) {
      getCurrentUser();
    }
  }, [loginResponse, getCurrentUser]);
  
  
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
          loading={loginLoading ? "true" : "false"}
          onFinish={(values: API.LoginParams) => {
            onFinish(values);
          }}
        >


          {loginError  && (
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
