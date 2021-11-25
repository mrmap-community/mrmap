import React from "react";

export interface AuthContextType {
  user: any;
  login: (user: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextType>(null!);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = React.useState('');

  function waitforme(milisec:number) {
    return new Promise(resolve => {
        setTimeout(() => { resolve('') }, milisec);
    })
}

  async function login(user: string, password: string): Promise<boolean> {
    // TODO: API call
    console.log ("TODO: API login call");
    await waitforme(2000);
    if (user === 'mrmap' && password === 'mrmap') {
      setUser(user);
      return Promise.resolve(true);
    }
    if (user === 'admin' && password === 'admin') {
      setUser(user);
      return Promise.resolve(true);
    }
    return Promise.resolve(false);
  }

  async function logout(): Promise<void> {
    // TODO: API call
    await waitforme(2000);
    console.log ("TODO: API logout call");
    setUser('');
  }

  let value = { user, login, logout };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return React.useContext(AuthContext);
}
