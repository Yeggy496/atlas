import type { Assignment } from "./types";

// Reuse lanes when events merely touch; share width within each overlap cluster.
export function calendarLanes(assignments: Assignment[]) {
  const layout = new Map<string, { lane: number; lanes: number }>();
  const sorted = [...assignments].sort(
    (a, b) => a.start - b.start || b.end - a.end || a.activity_id.localeCompare(b.activity_id),
  );
  let cluster: { id: string; lane: number }[] = [];
  let laneEnds: number[] = [];
  let clusterEnd = -1;
  const finish = () => {
    for (const event of cluster) {
      layout.set(event.id, { lane: event.lane, lanes: laneEnds.length });
    }
    cluster = [];
    laneEnds = [];
  };
  for (const event of sorted) {
    if (event.start >= clusterEnd) finish();
    let lane = laneEnds.findIndex((end) => end <= event.start);
    if (lane === -1) lane = laneEnds.length;
    laneEnds[lane] = event.end;
    cluster.push({ id: event.activity_id, lane });
    clusterEnd = Math.max(clusterEnd, event.end);
  }
  finish();
  return layout;
}
