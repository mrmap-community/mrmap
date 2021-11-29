import React, { useEffect } from "react";
import { notification } from 'antd';
import LoginRepo from "../Repos/LoginRepo";
import LogoutRepo from "../Repos/LogoutRepo";
import { hasOwnProperty, useLocalStorage } from "../utils";
import { UserRepo } from "../Repos/UserRepo";


export interface AuthContextType {
  user: any;
  userId: string;
  login: (user: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextType>(null!);

const loginRepo = new LoginRepo();
const logoutRepo = new LogoutRepo();
const userRepo = new UserRepo();

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState('');
  const [userId, setUserId] = useLocalStorage("userId", undefined);
  
  useEffect(() => {
    async function fetchCurrentUser() {
      const res = await userRepo.get(userId);
      if (res.status === 200
        && res.data
        && res.data.data
        && hasOwnProperty(res.data.data, 'attributes')
        && res.data.data.attributes){
        setUser(res.data.data.attributes);
        
        
      }
    } 
    if (userId){
      fetchCurrentUser();
    }
  }, [userId]);
  
  function waitforme(milisec:number) {
    return new Promise(resolve => {
        setTimeout(() => { resolve('') }, milisec);
    })
}

  async function login(user: string, password: string): Promise<boolean> {
    const res = await loginRepo.login({username: user, password: password});
    if (res.status === 200
      && res.data
      && res.data.data
      && hasOwnProperty(res.data.data, 'attributes')
      && res.data.data.attributes) {
        setUserId(res.data.data.id); 
        notification.success({
          message: 'Successfully logged in.',
        });
      return Promise.resolve(true);
    } else {
      notification.error({
        message: 'Failed to log in.',
      });
      return Promise.resolve(false);
    }
  }

  async function logout(): Promise<void> {
    setUser('');
    setUserId(undefined);
    const res = await logoutRepo.logout();
    /* TODO: 
         1. add success notification
    */
  }

  let value = { user, userId, login, logout };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return React.useContext(AuthContext);
}
