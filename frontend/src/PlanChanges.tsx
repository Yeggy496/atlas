import { type Assignment, type Problem, type Result, DAYS, clock } from "./types";

export interface PlanBaseline { problem: Problem; assignments: Assignment[] }
const when = (a: Assignment) => `${DAYS[Math.floor(a.start / 48)]} ${clock(a.start)}–${a.end % 48 === 0 ? "24:00" : clock(a.end)}`;

export function PlanChanges({ before, problem, result }: { before: PlanBaseline; problem: Problem; result: Result }) {
  if (!before.assignments.length || !["FEASIBLE", "OPTIMAL"].includes(result.status)) return null;
  const old = new Map(before.assignments.map((a) => [a.activity_id, a]));
  const now = new Map(result.assignments.map((a) => [a.activity_id, a]));
  const rows: { id: string; name: string; kind: string; text: string }[] = [];
  let kept = 0, moved = 0, added = 0, removed = 0;
  const room = (p: Problem, a: Assignment) => a.room_id ? ` · ${p.resources.find((r) => r.id === a.room_id)?.name ?? a.room_id}` : "";
  for (const id of new Set([...old.keys(), ...now.keys()])) {
    const a = old.get(id), b = now.get(id);
    const name = problem.activities.find((x) => x.id === id)?.name ?? before.problem.activities.find((x) => x.id === id)?.name ?? "已移除活动";
    if (a && b && a.start === b.start && a.end === b.end && a.room_id === b.room_id) kept++;
    else if (a && b) {
      moved++; rows.push({ id, name, kind: "调整", text: `${when(a)}${room(before.problem, a)} → ${when(b)}${room(problem, b)}` });
    } else if (b) {
      added++; rows.push({ id, name, kind: "新增安排", text: when(b) + room(problem, b) });
    } else if (a) {
      removed++; rows.push({ id, name, kind: "移出计划", text: when(a) + room(before.problem, a) });
    }
  }
  return <details className="plan-changes" open={rows.length > 0}>
    <summary>与上次安排相比 <span>保留 {kept} · 调整 {moved} · 新增 {added} · 移出 {removed}</span></summary>
    {rows.length ? <ul>{rows.map((r) => <li key={r.id}><strong>{r.name}<small>{r.kind}</small></strong><span>{r.text}</span></li>)}</ul> : <p>所有已有安排均已保留。</p>}
  </details>;
}
