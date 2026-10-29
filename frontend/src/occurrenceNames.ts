import type { Activity, Assignment, Problem } from "./types";

// Number interchangeable repeated activities by their actual order.
// Do not rename the underlying tasks or add mathematical constraints.
function occurrence(name: string): { base: string; number: number } | null {
  const match = name.match(/^(.+?)\s*[（(]第\s*(\d+|[一二三四五六七八九十]+)\s*次[）)]$/)
    ?? name.match(/^(.+?)\s*第\s*(\d+|[一二三四五六七八九十]+)\s*次$/)
    ?? name.match(/^(.+?)\s+(\d+)$/)
    ?? name.match(/^(.+?[\u3400-\u9fff])(\d+)$/);
  if (!match || !match[1].trim()) return null;
  const chinese: Record<string, number> = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 };
  const number = /^\d+$/.test(match[2]) ? Number(match[2]) : chinese[match[2]];
  return number ? { base: match[1].trim(), number } : null;
}

export function occurrenceNames(problem: Problem, assignments: Assignment[]): Map<string, string> {
  const names = new Map(problem.activities.map((a) => [a.id, a.name]));
  const chosen = new Map(assignments.map((x) => [x.activity_id, x]));
  const groups = new Map<string, Activity[]>();
  for (const a of problem.activities) {
    const match = occurrence(a.name);
    if (!match) continue;
    const key = match.base;
    groups.set(key, [...(groups.get(key) ?? []), a]);
  }
  const signature = (a: Activity) => JSON.stringify([a.category, a.duration, [...a.resources].sort(),
    Object.entries(a.demands).sort(), [...a.room_options].sort(), a.required_seats, a.room_type,
    [...a.days].sort(), a.window_start, a.window_end, a.priority]);
  // Per-activity preferences may be identical even when their IDs differ.
  // Fixed times or links between named tasks preserve the original identities.
  const individualRules = (a: Activity): string | null => {
    if (problem.constraints.some((c) => c.other === a.id)) return null;
    const rules = problem.constraints.filter((c) => c.target === a.id);
    if (rules.some((c) => c.type === "fixed_time" || c.other != null)) return null;
    return JSON.stringify(rules.map((c) => JSON.stringify([c.type, c.level, c.day, c.start, c.end, c.value])).sort());
  };
  for (const members of groups.values()) {
    if (members.length < 2 || members.some((a) => !chosen.has(a.id) || a.group || a.optional ||
      signature(a) !== signature(members[0]) || individualRules(a) === null || individualRules(a) !== individualRules(members[0]))) continue;
    const numbers = members.map((a) => occurrence(a.name)!.number).sort((a, b) => a - b);
    if (numbers.some((n, i) => n !== i + 1)) continue;
    const label = occurrence(members[0].name)!.base;
    members.sort((a, b) => chosen.get(a.id)!.start - chosen.get(b.id)!.start || a.id.localeCompare(b.id));
    members.forEach((a, index) => names.set(a.id, `${label}（第${index + 1}次）`));
  }
  return names;
}
