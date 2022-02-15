import React, { ReactElement } from 'react';
import { AuthContext } from '../Contexts/AuthContext/AuthContext';

const anonymousUser = undefined;

export function AuthProvider ({ children }: { children: React.ReactNode }): ReactElement {
  
  const [user, setUser] = React.useState(anonymousUser);

  const value = { user, setUser };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
