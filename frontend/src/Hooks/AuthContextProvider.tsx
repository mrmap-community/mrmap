import React, { useEffect } from "react";
import { notification } from 'antd';
import TokenObtainRepo from "../Repos/TokenObtainRepo";
import { isExpired, decodeToken } from "react-jwt";
import { hasOwnProperty } from "../utils";
import { UserRepo } from "../Repos/UserRepo";

export interface AuthContextType {
  user: any;
  login: (user: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextType>(null!);

const tokenRepo = new TokenObtainRepo();
const userRepo = new UserRepo();

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState('');
  const [userId, setUserId] = React.useState('');

  useEffect(() => {
    async function fetchCurrentUser() {
      try{
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
        }
      } catch (error) {
        console.log(error);
      }
    } 
    console.log(userId);
    if (userId){fetchCurrentUser();}
    
  }, [userId]);
  
  function waitforme(milisec:number) {
    return new Promise(resolve => {
        setTimeout(() => { resolve('') }, milisec);
    })
}

  async function login(user: string, password: string): Promise<boolean> {
    const res = await tokenRepo.obtain({username: user, password: password});
    if (res.status === 200
      && res.data
      && res.data.data
      && hasOwnProperty(res.data.data, 'attributes')
      && res.data.data.attributes) {
      
      const decodedToken = decodeToken(res.data.data.attributes.access);
      /* TODO: 
         1. get 'user_id' from decoded token
         2. obtain user object from user endpoint by the given id from 'user_id'
         3. set current user
         4. set auth header: 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX3BrIjoxLCJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiY29sZF9zdHVmZiI6IuKYgyIsImV4cCI6MTIzNDU2LCJqdGkiOiJmZDJmOWQ1ZTFhN2M0MmU4OTQ5MzVlMzYyYmNhOGJjYSJ9.NHlztMGER7UADHZJlxNG0WSi22a2KaYSfd1S-AuT7lU'
      
        Note: auth header should be stored in locale storage or cookie?
      
      */

        if(typeof decodedToken === 'object' 
        && decodedToken
        && hasOwnProperty(decodedToken, 'user_id') 
        && typeof decodedToken.user_id === 'string' 
        ) {
          setUserId(decodedToken.user_id);          
        }

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
    /* TODO: 
         1. delete auth header
         2. add success notification
    */
  }

  let value = { user, login, logout };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return React.useContext(AuthContext);
}
