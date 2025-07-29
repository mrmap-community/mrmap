import { useEffect, useState } from "react";
import { systemTimeStore } from "../../providers/systemTimeProvider";

export function useSystemTime(): string | null {
  const [time, setTime] = useState(() => systemTimeStore.get());
  
  useEffect(() => {
    const update = () => setTime(systemTimeStore.get());
    const unsubscribe = systemTimeStore.subscribe(update);
    return unsubscribe;
  }, []);

  return time;
}