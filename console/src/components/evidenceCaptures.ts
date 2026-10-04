import { api } from "../api/client";
import type { GoalContract } from "../api/types";
import { clock } from "../format";
import type { TimelineItem } from "../state/runReducer";

export interface Capture {
  src: string;
  label: string;
  capturedAt: string;
  revision?: string;
}

export interface CapturePair {
  source: Capture;
  saved: Capture;
}

export function evidenceCaptures(
  runId: string,
  contract: GoalContract | null,
  timeline: TimelineItem[],
  verified: boolean,
): CapturePair | undefined {
  if (!verified || contract?.sources.length !== 1) return undefined;
  const reference = contract.sources[0];
  const source = [...timeline].reverse().find((item) =>
    item.type === "step" && item.data.tool === "record_facts" && item.data.ok &&
    item.data.screenshot && item.data.url?.split("?")[0].endsWith(`/${reference.doc_id}`));
  const saved = [...timeline].reverse().find((item) =>
    item.type === "step" && item.data.tool === "submit_form" && item.data.ok &&
    item.data.screenshot && source && item.seq > source.seq);
  if (!source || !saved || source.type !== "step" || saved.type !== "step") return undefined;
  return {
    source: {
      src: api.artifactUrl(runId, source.data.screenshot!),
      label: reference.kind === "message" ? "Source message" : "Source invoice",
      revision: reference.revision,
      capturedAt: clock(source.ts),
    },
    saved: {
      src: api.artifactUrl(runId, saved.data.screenshot!),
      label: "Saved record",
      capturedAt: clock(saved.ts),
    },
  };
}
