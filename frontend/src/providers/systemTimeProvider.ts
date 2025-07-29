export const SYSTEM_TIME_LOCAL_STORAGE_NAME = "mrmap.systemTime"

const systemTimeEvents = new EventTarget();

/**
 * updated die gespeicherte Systemzeit nur, wenn
 * der neue ISO-String zeitlich später ist als der gespeicherte.
 * @param systemTime ISO-String z.B. "2025-07-29T11:19:33+02:00"
 */
export const updateSystemTime = (systemTime: string | undefined) => {
  if (!systemTime) return;

  const storedIsoString = localStorage.getItem(SYSTEM_TIME_LOCAL_STORAGE_NAME);

  if (storedIsoString) {
    const newTimeMs = Date.parse(systemTime);
    const storedTimeMs = Date.parse(storedIsoString);

    if (isNaN(newTimeMs)) {
      console.warn("Neuer ISO-Zeitstempel ist ungültig:", systemTime);
      return;
    }
    if (isNaN(storedTimeMs)) {
      // Falls gespeicherter String ungültig, überschreiben
      localStorage.setItem(SYSTEM_TIME_LOCAL_STORAGE_NAME, systemTime);
      systemTimeEvents.dispatchEvent(new Event("change")); // Trigger Event
      return;
    }

    if (newTimeMs > storedTimeMs) {
      localStorage.setItem(SYSTEM_TIME_LOCAL_STORAGE_NAME, systemTime);
      systemTimeEvents.dispatchEvent(new Event("change")); // Trigger Event
    }
  } else {
    // Kein gespeicherter Wert, also speichern
    localStorage.setItem(SYSTEM_TIME_LOCAL_STORAGE_NAME, systemTime);
    systemTimeEvents.dispatchEvent(new Event("change")); // Trigger Event
  }
};

export const systemTimeStore = {
  get: (): string | null => {
    return localStorage.getItem(SYSTEM_TIME_LOCAL_STORAGE_NAME);
  },
  subscribe: (callback: () => void) => {
    systemTimeEvents.addEventListener("change", callback);

    // Zusätzlich Storage-Event für andere Tabs abonnieren:
    const storageHandler = (event: StorageEvent) => {
      if (event.key === SYSTEM_TIME_LOCAL_STORAGE_NAME) callback();
    };
    window.addEventListener("storage", storageHandler);

    // Cleanup-Funktion
    return () => {
      systemTimeEvents.removeEventListener("change", callback);
      window.removeEventListener("storage", storageHandler);
    };
  }
};