import type { JsonApiDocument, JsonApiPrimaryData } from "./utils/jsonapi";

/**
 * @see https://umijs.org/zh-CN/plugins/plugin-access
 * */
export default function access(initialState: { currentUser?: JsonApiDocument } | undefined) {
  const { currentUser } = initialState ?? {};

  const userData = currentUser?.data as JsonApiPrimaryData;

  return {
    isAuthenticated: (userData && userData?.attributes?.username !== 'AnonymousUser') ? true : false,
    isSuperuser: (userData && userData?.attributes?.isSuperuser === true) ? true : false,
  };
}
