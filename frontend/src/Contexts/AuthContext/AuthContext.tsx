import React from 'react';

export interface AuthContextType {
  user: any;
  setUser: (user: any) => void;
}

export const AuthContext = React.createContext<AuthContextType|null>(null);
