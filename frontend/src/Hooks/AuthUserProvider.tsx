import React, { Context, FC, ReactElement, useContext, useState } from 'react';

import OpenApiRepo from '../Repos/OpenApiRepo';

export const AuthContext = React.createContext(undefined);

export const AuthProvider: FC<any> = ({ children }): ReactElement => {
  const [username, setUsername] = useState('guest');

  const handleAuth = ({ username, password }: { username: string, password: string }, action: string) => {
    // async function checkCurrentAuth() {
    //   const client = await api.getClient();
    //   debugger;
    //   const res = await client.v1_auth_user_retrieve()
    //   .catch(error => {
    //     console.log(error);
    //   });
    //   console.log(res);
    //   // 200 if logged in user
    //   // 403 if no authenticated used is present
    // }
    // checkCurrentAuth();

    async function loginUser (): Promise<void> {
      const client = await OpenApiRepo.getClientInstance();
      const res = await client.v1_auth_login_create({}, { username: username, password: password });
      if (res.status === 200) {
        setUsername(username);
      }
    }

    async function logoutUser (): Promise<void> {
      const client = await OpenApiRepo.getClientInstance();
      await client.v1_auth_logout_create();
    }

    switch (action) {
      case 'loginUser':
        loginUser();
        break;
      case 'logoutUser':
        logoutUser();
        break;
      default:
        break;
    }
  };
  const data = [username, handleAuth];
  return (<AuthContext.Provider value={data as any}>{children}</AuthContext.Provider>);
};

export const useAuth = (): Context<any> => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth can only be used inside AuthProvider');
  }
  return context;
};
