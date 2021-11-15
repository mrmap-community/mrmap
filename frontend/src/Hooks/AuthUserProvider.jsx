import React, { useContext, useState } from 'react';
import { OpenAPIContext } from "./OpenAPIProvider";


export const AuthContext = React.createContext();

export const AuthProvider = ({ children }) => {
    const [username, setUsername] = useState("guest");
    const { api } = useContext(OpenAPIContext);

    const handleAuth = ({ username, password }, action) => {
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


      async function loginUser() {
        const client = await api.getClient();
        const res = await client.v1_auth_login_create({},{username: username, password: password});
        console.log(res);
        if (res.status == 200){
          console.log("HUHU");
          setUsername(username);
        }
        console.log(username);
      }

      async function logoutUser(){
        const client = await api.getClient();
        const res = await client.v1_auth_logout_create();
        console.log(res);
      }

      switch (action) {
        case "loginUser":
          loginUser();
          break;
        case "logoutUser":
          logoutUser();
          break;
        default:
          break;
      }

    };
    const data = [username, handleAuth];
    return <AuthContext.Provider value={data}>{children}</AuthContext.Provider>;
  };
  

  export const useAuth = () => {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error("useAuth can only be used inside AuthProvider");
    }
    return context;
};
