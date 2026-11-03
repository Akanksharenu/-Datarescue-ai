import { useCallback, useEffect, useRef, useState } from "react";

/** The four states the guide asks every screen to handle: loading, empty, error, success. */
export type AsyncState<T> =
  | { status: "loading"; data?: T }
  | { status: "error"; error: string; data?: T }
  | { status: "success"; data: T };

/**
 * Run an async loader on mount (and whenever `deps` change). `reload` re-runs it while
 * keeping the previous data visible so the page does not flash empty during a refresh.
 */
export function useAsync<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  const latest = useRef(0);

  const run = useCallback(async () => {
    const ticket = ++latest.current;
    setState((prev) => ({ status: "loading", data: prev.data }));
    try {
      const data = await loader();
      if (ticket === latest.current) setState({ status: "success", data });
    } catch (err) {
      if (ticket === latest.current) {
        setState((prev) => ({ status: "error", error: errorMessage(err), data: prev.data }));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    void run();
  }, [run]);

  return { ...state, reload: run };
}

/** Track one in-flight action (a button click) with its own error and busy flag. */
export function useAction<Args extends unknown[], R>(action: (...args: Args) => Promise<R>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const invoke = useCallback(
    async (...args: Args): Promise<R | undefined> => {
      setBusy(true);
      setError(null);
      try {
        return await action(...args);
      } catch (err) {
        setError(errorMessage(err));
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [action],
  );

  return { invoke, busy, error, clearError: () => setError(null) };
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}
