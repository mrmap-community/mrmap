import React from 'react';

import { AuthContext, AuthContextType } from '../Contexts/AuthContext/AuthContext';


export function useAuth (): AuthContextType | null {
  return React.useContext(AuthContext);
}
