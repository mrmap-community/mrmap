import React from 'react';

export interface AuthContextType {
  user: any;
  login: (user: string, password: string) => Promise<boolean>;
  logout: () => Promise<boolean>;
}

export const AuthContext = React.createContext<AuthContextType|null>(null);
