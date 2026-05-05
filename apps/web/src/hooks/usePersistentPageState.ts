import {
  type Dispatch,
  type SetStateAction,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type StorageKind = "sessionStorage" | "localStorage";

interface PersistentPageStateOptions {
  version?: number;
  storage?: StorageKind;
  debounceMs?: number;
}

interface StoredEnvelope<T> {
  version: number;
  state: T;
}

function getStorage(kind: StorageKind): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window[kind] ?? null;
  } catch {
    return null;
  }
}

function readStoredState<T>(
  key: string,
  initialState: T,
  version: number,
  storageKind: StorageKind,
): T {
  const storage = getStorage(storageKind);
  if (!storage) {
    return initialState;
  }

  try {
    const raw = storage.getItem(key);
    if (!raw) {
      return initialState;
    }

    const parsed = JSON.parse(raw) as Partial<StoredEnvelope<T>>;
    if (!parsed || parsed.version !== version || !("state" in parsed)) {
      return initialState;
    }

    return parsed.state as T;
  } catch {
    return initialState;
  }
}

function writeStoredState<T>(
  key: string,
  state: T,
  version: number,
  storageKind: StorageKind,
): void {
  const storage = getStorage(storageKind);
  if (!storage) {
    return;
  }

  try {
    storage.setItem(key, JSON.stringify({ version, state }));
  } catch {
    // Storage quota and privacy-mode errors should not break page workflows.
  }
}

function clearStoredState(key: string, storageKind: StorageKind): void {
  const storage = getStorage(storageKind);
  if (!storage) {
    return;
  }

  try {
    storage.removeItem(key);
  } catch {
    // Ignore unavailable storage.
  }
}

export function usePersistentPageState<T>(
  key: string,
  initialState: T,
  options: PersistentPageStateOptions = {},
): [T, Dispatch<SetStateAction<T>>, () => void] {
  const version = options.version ?? 1;
  const storageKind = options.storage ?? "sessionStorage";
  const debounceMs = options.debounceMs ?? 150;
  const initialRef = useRef(initialState);
  const hasMountedRef = useRef(false);
  const writeTimerRef = useRef<number | null>(null);

  const [state, setState] = useState<T>(() =>
    readStoredState(key, initialRef.current, version, storageKind),
  );

  useEffect(() => {
    if (!hasMountedRef.current) {
      hasMountedRef.current = true;
      return undefined;
    }

    if (writeTimerRef.current !== null && typeof window !== "undefined") {
      window.clearTimeout(writeTimerRef.current);
    }

    if (debounceMs <= 0 || typeof window === "undefined") {
      writeStoredState(key, state, version, storageKind);
      return undefined;
    }

    writeTimerRef.current = window.setTimeout(() => {
      writeStoredState(key, state, version, storageKind);
      writeTimerRef.current = null;
    }, debounceMs);

    return () => {
      if (writeTimerRef.current !== null && typeof window !== "undefined") {
        window.clearTimeout(writeTimerRef.current);
        writeTimerRef.current = null;
      }
    };
  }, [debounceMs, key, state, storageKind, version]);

  const reset = useCallback(() => {
    if (writeTimerRef.current !== null && typeof window !== "undefined") {
      window.clearTimeout(writeTimerRef.current);
      writeTimerRef.current = null;
    }
    clearStoredState(key, storageKind);
    setState(initialRef.current);
  }, [key, storageKind]);

  return useMemo(() => [state, setState, reset], [reset, state]);
}

export function readPersistentPageState<T>(
  key: string,
  initialState: T,
  options: PersistentPageStateOptions = {},
): T {
  return readStoredState(
    key,
    initialState,
    options.version ?? 1,
    options.storage ?? "sessionStorage",
  );
}

export function clearPersistentPageState(
  key: string,
  options: PersistentPageStateOptions = {},
): void {
  clearStoredState(key, options.storage ?? "sessionStorage");
}
