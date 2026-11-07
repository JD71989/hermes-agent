import { useCallback, useEffect, useRef, useState } from "react";

import { errorMessage } from "@/lib/api-error";

/**
 * Loader for a read-only Guardian surface: keeps the previous payload visible
 * while refreshing (no flash of empty state) and exposes the error so the page
 * can render `LoadErrorNotice` instead of an empty dashboard.
 *
 * The initial load and the poll both run without the spinner — only the
 * explicit refresh sets `loading`, so a background poll never blanks the UI.
 */
export function useGuardianSurface<T>(load: () => Promise<T>, intervalMs = 30_000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);

  useEffect(() => {
    loadRef.current = load;
  }, [load]);

  const fetchNow = useCallback(async () => {
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    await fetchNow();
  }, [fetchNow]);

  useEffect(() => {
    void fetchNow();
    if (intervalMs <= 0) return;
    const id = window.setInterval(() => void fetchNow(), intervalMs);
    return () => window.clearInterval(id);
  }, [fetchNow, intervalMs]);

  return { data, error, loading, refresh };
}
