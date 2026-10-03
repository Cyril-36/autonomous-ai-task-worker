import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../api/client";
import { openRunStream } from "../api/stream";
import { TERMINAL_STATUSES, type Budget, type RunEvent } from "../api/types";
import { applyEvent, hydrate, type RunView } from "./runReducer";

export interface RunState {
  view: RunView | null;
  budget: Budget | null;
  error: ApiError | null;
  connected: boolean;
  /** seqs that arrived live (not replay); rows animate in once */
  freshSeqs: ReadonlySet<number>;
  refresh: () => void;
}

export function useRun(runId: string | null): RunState {
  const [view, setView] = useState<RunView | null>(null);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [connected, setConnected] = useState(false);
  const [fresh, setFresh] = useState<ReadonlySet<number>>(new Set());
  const [nonce, setNonce] = useState(0);
  const replaying = useRef(true);

  useEffect(() => {
    if (!runId) return;
    let closeStream: (() => void) | null = null;
    let cancelled = false;
    setView(null);
    setError(null);
    setFresh(new Set());
    replaying.current = true;

    api
      .run(runId)
      .then((detail) => {
        if (cancelled) return;
        setBudget(detail.budget);
        setView(hydrate(detail));
        const replayUntil = detail.last_seq;
        closeStream = openRunStream(runId, 0, {
          onEvent: (event: RunEvent) => {
            setView((v) => (v ? applyEvent(v, event) : v));
            if (event.seq > replayUntil) setFresh((s) => new Set(s).add(event.seq));
            if (event.type === "cost") {
              setBudget((b) => (b ? { ...b, global_spent_inr: event.data.global_spent_inr, run_spent_inr: event.data.run_spent_inr } : b));
            }
          },
          onEnd: () => setConnected(false),
          onConnectionChange: setConnected,
        });
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof ApiError ? e : new ApiError(0, "unexpected", "Couldn't load this run."));
      });

    return () => {
      cancelled = true;
      closeStream?.();
    };
  }, [runId, nonce]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  return { view, budget, error, connected, freshSeqs: fresh, refresh };
}

export function isTerminal(view: RunView | null): boolean {
  return view ? TERMINAL_STATUSES.has(view.status) : false;
}
