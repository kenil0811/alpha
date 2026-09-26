import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Poll while `key` is set: every `intervalMs`, and after a failed request keep going with a
 * growing delay (at most 10 s) instead of stopping. A failed status request says nothing about
 * the work itself, so it is reported as "reconnecting", never as a failure of that work.
 * Stops when `key` becomes null or the component unmounts.
 */
export function usePoll<T>(
  key: string | null,
  fetch: () => Promise<T>,
  onResult: (value: T) => void,
  intervalMs = 1000,
) {
  const [failures, setFailures] = useState(0);
  const [generation, setGeneration] = useState(0);
  const fetchRef = useRef(fetch);
  const resultRef = useRef(onResult);
  fetchRef.current = fetch;
  resultRef.current = onResult;

  useEffect(() => {
    if (!key) {
      setFailures(0);
      return;
    }
    let cancelled = false;
    let timer: number | undefined;
    let misses = 0;
    const tick = async () => {
      try {
        const value = await fetchRef.current();
        if (cancelled) return;
        misses = 0;
        setFailures(0);
        resultRef.current(value);
      } catch {
        if (cancelled) return;
        misses += 1;
        setFailures(misses);
      }
      if (!cancelled) {
        const delay = misses ? Math.min(intervalMs * 2 ** misses, 10_000) : intervalMs;
        timer = window.setTimeout(tick, delay);
      }
    };
    timer = window.setTimeout(tick, generation ? 0 : intervalMs);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [key, intervalMs, generation]);

  /** Ask again now (restarts the loop with an immediate request). */
  const refresh = useCallback(() => setGeneration((g) => g + 1), []);
  return { reconnecting: failures > 0, failures, refresh };
}
