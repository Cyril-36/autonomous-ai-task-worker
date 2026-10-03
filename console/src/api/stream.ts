import type { RunEvent, RunEventType } from "./types";

const EVENT_TYPES: RunEventType[] = [
  "run_status",
  "phase",
  "plan",
  "step",
  "fact",
  "contract",
  "gate",
  "approval",
  "question",
  "answer",
  "pending",
  "verification",
  "cost",
  "error",
];

/** Passes each seq once, in the order received; drops replays and duplicates. */
export class SeqGate {
  private last: number;

  constructor(lastSeen = 0) {
    this.last = lastSeen;
  }

  accept(event: Pick<RunEvent, "seq">): boolean {
    if (event.seq <= this.last) return false;
    this.last = event.seq;
    return true;
  }

  get lastSeq(): number {
    return this.last;
  }
}

export interface StreamHandlers {
  onEvent: (event: RunEvent) => void;
  onEnd: () => void;
  onConnectionChange: (connected: boolean) => void;
}

/**
 * Subscribes to a run's event stream. The server replays from Last-Event-ID
 * (sent automatically by EventSource on reconnect) or from the start; SeqGate
 * removes anything already applied. Returns a function that closes the stream.
 */
export function openRunStream(runId: string, lastSeq: number, handlers: StreamHandlers): () => void {
  const gate = new SeqGate(lastSeq);
  const source = new EventSource(`/api/runs/${encodeURIComponent(runId)}/stream`, { withCredentials: true });
  let closed = false;

  const onMessage = (msg: MessageEvent<string>) => {
    let event: RunEvent;
    try {
      event = JSON.parse(msg.data) as RunEvent;
    } catch {
      return;
    }
    if (gate.accept(event)) handlers.onEvent(event);
  };

  for (const type of EVENT_TYPES) source.addEventListener(type, onMessage as EventListener);
  source.addEventListener("end", () => {
    closed = true;
    source.close();
    handlers.onConnectionChange(false);
    handlers.onEnd();
  });
  source.onopen = () => handlers.onConnectionChange(true);
  source.onerror = () => {
    if (!closed) handlers.onConnectionChange(false);
  };

  return () => {
    closed = true;
    source.close();
  };
}
