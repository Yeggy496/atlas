import type { Activity, Assignment, Problem } from "./types";

// Number otherwise interchangeable repeated courses by their actual order.
// Do not rename the underlying tasks or add mathematical constraints.
export function occurrenceNames(problem: Problem, assignments: Assignment[]): Map<string, string> {
  const names = new Map(problem.activities.map((a) => [a.id, a.name]));
  if (problem.scenario !== "academic") return names;
  const chosen = new Map(assignments.map((x) => [x.activity_id, x]));
  const groups = new Map<string, Activity[]>();
  for (const a of problem.activities) {
    const match = a.name.match(/^(.*?)\s*[（(]第\s*(\d+)\s*次[）)]$/);
    if (!match || !match[1].trim()) continue;
    const key = match[1].trim();
    groups.set(key, [...(groups.get(key) ?? []), a]);
  }
  const signature = (a: Activity) => JSON.stringify([a.category, a.duration, [...a.resources].sort(),
    Object.entries(a.demands).sort(), [...a.room_options].sort(), a.required_seats, a.room_type,
    [...a.days].sort(), a.window_start, a.window_end, a.priority]);
  for (const members of groups.values()) {
    if (members.length < 2 || members.some((a) => !chosen.has(a.id) || a.group || a.optional ||
      signature(a) !== signature(members[0]) || problem.constraints.some((c) => c.target === a.id || c.other === a.id))) continue;
    const numbers = members.map((a) => Number(a.name.match(/第\s*(\d+)\s*次/)?.[1])).sort((a, b) => a - b);
    if (numbers.some((n, i) => n !== i + 1)) continue;
    const label = members[0].name.replace(/\s*[（(]第\s*\d+\s*次[）)]$/, "");
    members.sort((a, b) => chosen.get(a.id)!.start - chosen.get(b.id)!.start || a.id.localeCompare(b.id));
    members.forEach((a, index) => names.set(a.id, `${label}（第${index + 1}次）`));
  }
  return names;
}
