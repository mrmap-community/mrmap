import React, { useEffect } from "react";
import { notification } from 'antd';
import LoginRepo from "../Repos/LogintRepo";
import LogoutRepo from "../Repos/LogoutRepo";
import { hasOwnProperty } from "../utils";
import { UserRepo } from "../Repos/UserRepo";
import { useLocation, useNavigate } from "react-router-dom";

export interface AuthContextType {
  user: any;
  login: (user: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextType>(null!);

const loginRepo = new LoginRepo();
const logoutRepo = new LogoutRepo();
const userRepo = new UserRepo();

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState('');
  // TODO: store userId in local storage...
  const [userId, setUserId] = React.useState('');
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from?.pathname || "/";
  useEffect(() => {
    async function fetchCurrentUser() {
      const res = await userRepo.get(userId);
      if (res.status === 200
        && res.data
        && res.data.data
        && hasOwnProperty(res.data.data, 'attributes')
        && res.data.data.attributes){
        setUser(res.data.data.attributes);
        notification.success({
          message: 'Successfully logged in.',
        });
        navigate(from, { replace: true });
      }
    } 
    console.log(userId);
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
    setUserId('');
    const res = await logoutRepo.logout();
    /* TODO: 
         1. delete session cookie
         2. add success notification
    */
  }

  let value = { user, login, logout };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return React.useContext(AuthContext);
}
