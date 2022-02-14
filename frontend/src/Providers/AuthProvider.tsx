import React, { ReactElement } from 'react';
import { AuthContext } from '../Contexts/AuthContext/AuthContext';
import AuthRepo from '../Repos/AuthRepo';

const authRepo = new AuthRepo();
const anonymousUser = undefined;

export function AuthProvider ({ children }: { children: React.ReactNode }): ReactElement {
  
  const [user, setUser] = React.useState(anonymousUser);

  async function login (_user: string, password: string): Promise<boolean> {
    try {
      const res = await authRepo.login({ username: _user, password: password });
      if (res.status === 200 ) {
        const currentUser = await authRepo.whoAmI();
        setUser(currentUser.data as any);
        return Promise.resolve(true);
      } else {
        return Promise.resolve(false);
      }
    } catch (err: any) {
      return Promise.resolve(false);
    }
  }

  async function logout (): Promise<boolean> {
    try {
      const res = await authRepo.logout();
      if (res.status === 200) {
        setUser(anonymousUser);
        return Promise.resolve(true);
      }
    } catch (err: any) {
      return Promise.resolve(false);
    }
    return Promise.resolve(false);
  }

  const value = { user, login, logout };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
