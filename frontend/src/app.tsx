import RightContent from '@/components/RightContent';
import { GithubFilled, LinkOutlined } from '@ant-design/icons';
import type { Settings as LayoutSettings } from '@ant-design/pro-layout';
import { PageLoading, SettingDrawer } from '@ant-design/pro-layout';
import type { AxiosRequestConfig } from 'axios';
import React from 'react';
import { OpenAPIProvider } from 'react-openapi-client';
import type { RunTimeLayoutConfig } from 'umi';
import { history, Link, request } from 'umi';
import defaultSettings from '../config/defaultSettings';
const isDev = process.env.NODE_ENV === 'development';
const loginPath = '/user/login';
/** 获取用户信息比较慢的时候会展示一个 loading */
export const initialStateConfig = {
  loading: <PageLoading />,
};

/**
 * @see  https://umijs.org/zh-CN/plugins/plugin-initial-state
 * */
export async function getInitialState(): Promise<{
  settings?: Partial<LayoutSettings>;
  currentUser?: any;
  loading?: boolean;
  fetchUserInfo?: () => Promise<any | undefined>;
}> {

  async function fetchCurrentUser(options?: Record<string, any>) {
    return request<{
      data: any; // TODO: jsonapi response object as type
    }>('/api/v1/accounts/who-am-i/', {
      method: 'GET',
      ...(options || {}),
    });
  }
  console.log('initial state called');
  console.log(history);
  const fetchUserInfo = async () => {
    try {
      const msg = await fetchCurrentUser();
      console.log(msg);
      return msg.data;
    } catch (error) {
      history.push(loginPath);
    }
    return undefined;
  };
  // 如果是登录页面，不执行
  if (history.location.pathname !== loginPath) {
    
    const currentUser = await fetchUserInfo();
    return {
      fetchUserInfo,
      currentUser,
      settings: defaultSettings,
    };
  }
  return {
    fetchUserInfo,
    settings: defaultSettings,
  };
}

// ProLayout 支持的api https://procomponents.ant.design/components/layout
export const layout: RunTimeLayoutConfig = ({ initialState, setInitialState }) => {
  return {
    rightContentRender: () => <RightContent />,
    disableContentMargin: false,
    waterMarkProps: {
      content: initialState?.currentUser?.name,
    },
    // footerRender: () => <Footer />,
    onPageChange: () => {
      const { location } = history;
      // 如果没有登录，重定向到 login
      if (!initialState?.currentUser && location.pathname !== loginPath) {
        history.push(loginPath);
      }
    },
    links: isDev
      ? [
          <Link key="openapi" to="/api/schema/" target="_blank">
            <LinkOutlined />
            <span>OpenAPI Schema</span>
          </Link>,
          <Link key="github" to="https://github.com/mrmap-community/mrmap" target="_blank">
            <GithubFilled />
            <span>Git</span>
          </Link>
          
        ]
      : [],
    menuHeaderRender: undefined,
    // 自定义 403 页面
    // unAccessible: <div>unAccessible</div>,
    // 增加一个 loading 的状态
    childrenRender: (children, props) => {
      // if (initialState?.loading) return <PageLoading />;
      return (
        <>
          {children}
          {!props.location?.pathname?.includes('/login') && (
            <SettingDrawer
              disableUrlParams
              settings={initialState?.settings}
              onSettingChange={(settings) => {
                setInitialState((preInitialState: any) => ({
                  ...preInitialState,
                  settings,
                }));
              }}
            />
          )}
        </>
      );
    },
    ...initialState?.settings,
  };
};

const defaultConfig: AxiosRequestConfig = {
  baseURL: '/',
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
  headers: {
    'Content-Type': 'application/vnd.api+json'
  }
};

export function rootContainer(container: any) {
  return <OpenAPIProvider 
    definition='/api/schema/'
    axiosConfigDefaults={defaultConfig}>
      { container }
  </OpenAPIProvider>
}