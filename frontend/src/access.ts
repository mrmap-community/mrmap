import type { JsonApiPrimaryData } from './utils/jsonapi';

/**
 * @see https://umijs.org/zh-CN/plugins/plugin-access
 * */
export default function access(initialState: { currentUser?: JsonApiPrimaryData } | undefined) {
  const { currentUser } = initialState ?? {};
  return {
    isAuthenticated:
      currentUser && currentUser?.attributes?.username !== 'AnonymousUser' ? true : false,
    isSuperuser: currentUser && currentUser?.attributes?.isSuperuser === true ? true : false,
  };
}
