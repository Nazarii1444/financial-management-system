import { DependencyList, useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react';

// ── "Data changed" signal ────────────────────────────────────────────────────
// Mutations call notifyDataChanged(); every useApi() refetches, so widgets
// elsewhere on screen (top bar, alerts) stay in sync without a global store.

let version = 0;
const listeners = new Set<() => void>();

export function notifyDataChanged() {
  version += 1;
  listeners.forEach((l) => l());
}

function useDataVersion() {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => version,
  );
}

// ── Fetch hook ───────────────────────────────────────────────────────────────

export interface ApiState<T> {
  data: T | undefined;
  error: unknown;
  loading: boolean;
  reload: () => void;
  setData: (data: T) => void;
}

export function useApi<T>(fetcher: () => Promise<T>, deps: DependencyList = [], enabled = true): ApiState<T> {
  const dataVersion = useDataVersion();
  const [data, setData] = useState<T>();
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(enabled);
  const [tick, setTick] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetcherRef
      .current()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, tick, dataVersion]);

  const reload = useCallback(() => setTick((n) => n + 1), []);

  return { data, error, loading, reload, setData };
}
