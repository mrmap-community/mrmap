import { useEffect, useState } from 'react';

export function hasOwnProperty<X extends {}, Y extends PropertyKey>
(obj: X, prop: Y): obj is X & Record<Y, unknown> {
  return obj.hasOwnProperty(prop);
}

function getStorageValue (key: string, defaultValue: any) {
  return localStorage.getItem(key) || defaultValue;
}

export const useLocalStorage = (key: string, defaultValue: any):any => {
  const [value, setValue] = useState(() => {
    return getStorageValue(key, defaultValue);
  });

  useEffect(() => {
    localStorage.setItem(key, value);
  }, [key, value]);

  return [value, setValue];
};
