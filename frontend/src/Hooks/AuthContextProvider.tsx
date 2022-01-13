import React, { ReactElement, useEffect } from 'react';
import LoginRepo from '../Repos/LoginRepo';
import LogoutRepo from '../Repos/LogoutRepo';
import UserRepo from '../Repos/UserRepo';
import { useLocalStorage } from '../utils';


export interface AuthContextType {
  user: any;
  userId: string;
  login: (user: string, password: string) => Promise<boolean>;
  logout: () => Promise<boolean>;
}

// eslint-disable-next-line
const AuthContext = React.createContext<AuthContextType>(null!);

const loginRepo = new LoginRepo();
const logoutRepo = new LogoutRepo();
const userRepo = new UserRepo();

export function AuthProvider ({ children }: { children: React.ReactNode }): ReactElement {
  const [user, setUser] = React.useState('');
  const [userId, setUserId] = useLocalStorage('userId', '');

  // on first initialization & when user id changes, fetch user information
  useEffect(() => {
    async function fetchCurrentUser () {
      try {
        const res = await userRepo.get(userId);
        if (res.status === 200 &&
        res.data &&
        res.data.data &&
        // TODO remove this after backend is fixed
        (res.data.data as any).attributes) {
          setUser((res.data.data as any).attributes);
        } else {
          // not 200 -> no session for user in backend
          setUserId('');
        }
      } catch (err: any) {
        // exception -> force logout
        setUserId('');
      }
    }
    if (userId) {
      fetchCurrentUser();
    }
  }, [userId, setUserId]);

  async function login (_user: string, password: string): Promise<boolean> {
    try {
      const res = await loginRepo.login({ username: _user, password: password });
      if (res.status === 200 &&
      res.data &&
      res.data.data &&
      // TODO remove this after backend is fixed
      (res.data.data as any).id) {
        setUserId((res.data.data as any).id);
        return Promise.resolve(true);
      } else {
        return Promise.resolve(false);
      }
    } catch (err: any) {
      return Promise.resolve(false);
    }
  }

  async function logout (): Promise<boolean> {
    setUser('');
    setUserId('');
    localStorage.setItem('schema', '');
    try {
      const res = await logoutRepo.logout();
      if (res.status === 200) {
        return Promise.resolve(true);
      }
    } catch (err: any) {
      return Promise.resolve(false);
    }
    return Promise.resolve(false);
  }

  const value = { user, userId, login, logout };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth (): AuthContextType {
  return React.useContext(AuthContext);
}
