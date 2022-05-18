import Footer from '@/components/Footer';
import { LockOutlined, UserOutlined } from '@ant-design/icons';
import { LoginForm, ProFormText } from '@ant-design/pro-form';
import { Alert, message } from 'antd';
import type { RequestPayload } from 'openapi-client-axios';
import type { ReactElement } from 'react';
import React, { useCallback, useEffect } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { FormattedMessage, history, SelectLang, useAccess, useIntl, useModel } from 'umi';
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
    { error: loginError, response: loginResponse, loading: loginLoading },
  ] = useOperationMethod('addLoginRequest');
  const [
    getCurrentUser,
    { error: currentUserError, response: currentUserResponse, loading: currentUserLoading },
  ] = useOperationMethod('getCurrentUser');
  const { isAuthenticated } = useAccess();

  /**
   * @description handles successfully login process; redirects to the last page
   */
  useEffect(() => {
    if (currentUserResponse && currentUserResponse.status === 200) {
      const defaultLoginSuccessMessage = intl.formatMessage({ id: 'pages.login.success' });
      message.success(defaultLoginSuccessMessage);
      setInitialState((currentState: any) => {
        const newState = currentState;
        if (currentUserResponse?.data?.data?.attributes?.settings) {
          newState.settings = currentUserResponse?.data?.data?.attributes?.settings;
        }
        return ({
          ...newState,
          userInfoResponse: currentUserResponse,
          currentUser: currentUserResponse.data.data,
          
        })
      });
    }
  }, [currentUserResponse, intl, setInitialState]);

  useEffect(() => {
    if (isAuthenticated && history) {
      /** Redirect to the page specified by redirect parameter */
      const { query } = history.location;
      const { redirect } = query as { redirect: string };
      history.push(redirect || '/');
    }
  }, [isAuthenticated]);

  /**
   * @description triggers get current user request if login was successfully
   */
  useEffect(() => {
    if (loginResponse && loginResponse.status === 200) {
      getCurrentUser();
    }
  }, [getCurrentUser, intl, loginResponse]);

  /**
   * @description handles errors on login processing
   */
  useEffect(() => {
    if (loginError || currentUserError) {
      const defaultLoginFailureMessage = intl.formatMessage({ id: 'pages.login.failure' });
      message.error(defaultLoginFailureMessage);
    }
  }, [intl, loginError, currentUserError]);

  /**
   * @description callback function to start login processing
   */
  const onFinish = useCallback(
    (values: any) => {
      const jsonApiPayload: RequestPayload = {
        data: {
          type: 'LoginRequest',
          attributes: {
            username: values.username,
            password: values.password,
          },
        },
      };
      createLoginRequest(undefined, jsonApiPayload);
    },
    [createLoginRequest],
  );

  const isLoggingIn = loginLoading || currentUserLoading;

  return (
    <div className={styles.container}>
      <div className={styles.lang} data-lang>
        {SelectLang && <SelectLang />}
      </div>
      <div className={styles.content}>
        <LoginForm
          logo={<img alt="mr. map logo" src="/logo.png" />}
          subTitle={intl.formatMessage({ id: 'pages.layouts.userLayout.title' })}
          initialValues={{
            autoLogin: true,
          }}
          onFinish={async (values) => {
            onFinish(values);
          }}
          submitter={{
            submitButtonProps: {
              loading: isLoggingIn,
              size: 'large',
              style: {
                width: '100%',
              },
            },
          }}
        >
          {loginError && (
            <LoginMessage
              content={intl.formatMessage({ id: 'pages.login.accountLogin.errorMessage' })}
            />
          )}
          <ProFormText
            name="username"
            fieldProps={{
              size: 'large',
              prefix: <UserOutlined className={styles.prefixIcon} />,
            }}
            placeholder={intl.formatMessage({ id: 'pages.login.username.placeholder' })}
            rules={[
              {
                required: true,
                message: <FormattedMessage id="pages.login.username.required" />,
              },
            ]}
            disabled={isLoggingIn}
          />
          <ProFormText.Password
            name="password"
            fieldProps={{
              size: 'large',
              prefix: <LockOutlined className={styles.prefixIcon} />,
            }}
            placeholder={intl.formatMessage({ id: 'pages.login.password.placeholder' })}
            rules={[
              {
                required: true,
                message: <FormattedMessage id="pages.login.password.required" />,
              },
            ]}
            disabled={isLoggingIn}
          />
        </LoginForm>
      </div>
      <Footer />
    </div>
  );
};

export default Login;
