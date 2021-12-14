import { useEffect, useState } from 'react';

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
