import React from 'react';

export interface AuthContextType {
  user: any;
  userId: string;
  login: (user: string, password: string) => Promise<boolean>;
  logout: () => Promise<boolean>;
}

export const AuthContext = React.createContext<AuthContextType|null>(null);
