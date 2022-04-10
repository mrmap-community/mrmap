/**
 * @see https://umijs.org/zh-CN/plugins/plugin-access
 * */
export default function access(initialState: { currentUser?: any } | undefined) {
  const { currentUser } = initialState ?? {};
  
  // TODO: just example of how to provide permissions 
  return {
    canAdmin: currentUser && currentUser.access === 'admin',
  };
}
