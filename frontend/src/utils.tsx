import { useEffect, useState } from 'react';

function getStorageValue(key: string, defaultValue: any) {
  return localStorage.getItem(key) || defaultValue;
}

export const useLocalStorage = (key: string, defaultValue: unknown):any => {
  const [value, setValue] = useState(() => getStorageValue(key, defaultValue));

  useEffect(() => {
    localStorage.setItem(key, value);
  }, [key, value]);

  return [value, setValue];
};
