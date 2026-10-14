import { CATEGORIES, DAYS, type Constraint, type Problem, clock } from "./types";

/** Describe the fields actually sent to the solver; user labels are only notes. */
export function describeConstraint(c: Constraint, problem: Problem): string {
  const target = (value: string | null) => value === "*" ? "全部活动"
    : problem.activities.find((a) => a.id === value)?.name
      ?? problem.resources.find((r) => r.id === value)?.name
      ?? CATEGORIES[value ?? ""]?.label ?? value ?? "未选择活动";
  const date = c.day === null ? "每天" : DAYS[c.day];
  const time = (slot: number) => slot === 48 ? "24:00" : clock(slot);
  const name = target(c.target);
  switch (c.type) {
    case "fixed_time": return `${name} · ${date} ${time(c.start)} 固定开始`;
    case "unavailable": return `${name} · ${date} ${time(c.start)}–${time(c.end)} 不可用`;
    case "time_window": return `${name} · ${date} 仅在 ${time(c.start)}–${time(c.end)} 内安排`;
    case "preferred_window": return `${name} · ${date} 尽量在 ${time(c.start)}–${time(c.end)} 内安排`;
    case "deadline": {
      const day = c.end === 0 ? 0 : Math.min(6, Math.floor((c.end - 1) / 48));
      const local = c.end - day * 48;
      return `${name} · ${DAYS[day]} ${time(local)} 前完成`;
    }
    case "daily_limit": return `${name} · ${date}最多 ${c.value} 次`;
    case "precedence": return `${name} 完成后再开始 ${target(c.other)}`;
    case "min_gap": return `${name} 完成后至少间隔 ${c.value / 2} 小时，再开始 ${target(c.other)}`;
    case "consecutive": return `${name} 完成后紧接 ${target(c.other)}`;
  }
}
