import RightContent from '@/components/RightContent';
import { GithubFilled, LinkOutlined } from '@ant-design/icons';
import type { Settings as LayoutSettings } from '@ant-design/pro-layout';
import { SettingDrawer } from '@ant-design/pro-layout';
import type { RunTimeLayoutConfig } from 'umi';
import { history, Link, request } from 'umi';
import defaultSettings from '../config/defaultSettings';
import PageLoading from './components/PageLoading';
import RootContainer from './components/RootContainer';
import type { JsonApiPrimaryData, JsonApiResponse } from './utils/jsonapi';

const isDev = process.env.NODE_ENV === 'development';
const loginPath = '/user/login';

const fetchUserInfo = async () => {
  try {
    const response = await request<JsonApiResponse>('/api/v1/accounts/who-am-i/', {
      method: 'GET',
    });
    const currentUser = response?.data as JsonApiPrimaryData;
    if (currentUser?.attributes) {
      currentUser.attributes.avatar =
        'https://gw.alipayobjects.com/zos/antfincdn/XAosXuNZyF/BiazfanxmamNRoxxVxka.png';
    }
    response.data = currentUser;

    return response;
  } catch (error) {
    history.push(loginPath);
  }
  return undefined;
};

/**
 * This function will be executed once at the start of the application.
 * <p>
 * The return value is available globally via <code>useModel('@@initialState')</code>.
 * <p>
 * @see https://umijs.org/zh-CN/plugins/plugin-initial-state
 */
export async function getInitialState(): Promise<{
  settings?: Partial<LayoutSettings>;
  userInfoResponse?: JsonApiResponse;
  currentUser?: JsonApiPrimaryData;
  isAuthenticated: boolean;
  loading?: boolean;
  fetchUserInfo?: () => Promise<JsonApiResponse | undefined>;
}> {
  const response = await fetchUserInfo();
  const currentUser = response?.data as JsonApiPrimaryData;
  const isAuthenticated = currentUser?.attributes.username !== 'AnonymousUser' ? true : false;
  return {
    fetchUserInfo: fetchUserInfo,
    userInfoResponse: response,
    currentUser: currentUser,
    isAuthenticated: isAuthenticated,
    settings: isAuthenticated ? currentUser?.attributes.settings : {layout: defaultSettings},
  };
}

/** When obtaining user information is slow, a loading */
export const initialStateConfig = {
  loading: <PageLoading />,
};

// ProLayout api https://procomponents.ant.design/components/layout
export const layout: RunTimeLayoutConfig = ({
  initialState,
  setInitialState,
}: {
  initialState: any;
  setInitialState: any;
}) => {
  return {
    rightContentRender: () => <RightContent />,
    disableContentMargin: false,
    // footerRender: () => <Footer />,
    links: isDev
      ? [
          <Link key="openapi" to="/api/schema/" target="_blank">
            <LinkOutlined />
            <span>OpenAPI Schema</span>
          </Link>,
          <Link key="github" to="https://github.com/mrmap-community/mrmap" target="_blank">
            <GithubFilled />
            <span>Git</span>
          </Link>,
        ]
      : [],
    // onPageChange: (location) => {
    //   // if not logged in, redirect to login page
    //   // if (!initialState.isAuthenticated) {
    //   //   history.push(loginPath);
    //   // }
    //   // if (initialState.isAuthenticated && location?.pathname === loginPath){
    //   //   history.push("/");
    //   // }
    // },
    //menuHeaderRender: undefined,
    //menu: loopMenuItem(defaultMenus),
    // custom 403 page
    // subMenuItemRender: (_, dom) => <div>pre {dom}</div>,
    // menuItemRender: (item, dom) => <div>{item.icon} {dom}</div>,
    menuProps: { forceSubMenuRender: true },
    // unAccessible: <div>unAccessible</div>,
    childrenRender: (children, props) => {
      // add a loading state
      // if (initialState?.loading) return <PageLoading />;
      return (
        <>
          {children}
          {!props.location?.pathname?.includes('/login') && (
            <SettingDrawer
              enableDarkTheme
              settings={initialState?.settings?.layout}
              onSettingChange={(layoutSettings) => {
                setInitialState((preInitialState: any) => ({
                  ...preInitialState,
                  settings: {
                    ...preInitialState.settings,
                    ['layout']: layoutSettings
                  },
                }));
              }}
            />
          )}
        </>
      );
    },
    ...initialState?.settings?.layout,
  };
};

export function rootContainer(container: any) {
  return <RootContainer>{container}</RootContainer>;
}
