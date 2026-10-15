import { useState } from "react";
import { Dialog } from "./Editors";
import { DAYS, id, type Activity, type Constraint, type Problem } from "./types";

export function RepeatActivity({ activity, problem, onClose, onSave }: {
  activity: Activity; problem: Problem; onClose: () => void;
  onSave: (activities: Activity[], constraints: Constraint[]) => Promise<void>;
}) {
  const [days, setDays] = useState<number[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const fixed = problem.constraints.find((c) => c.type === "fixed_time" && c.target === activity.id);
  return <Dialog title={`重复活动 · ${activity.name}`} dirty={days.length > 0} busy={saving} onClose={() => { if (!saving) onClose(); }}>
    <form onSubmit={async (event) => {
      event.preventDefault();
      if (!days.length || saving) return;
      setSaving(true); setError("");
      const copies = days.map((day) => ({ ...activity, id: id(), name: `${Array.from(activity.name).slice(0, 94).join("")} · ${DAYS[day]}`, days: [day], group: null, op_index: 0 }));
      const constraints = copies.flatMap((a) => problem.constraints
        .filter((c) => c.target === activity.id && !c.other && !["precedence", "min_gap", "daily_limit"].includes(c.type))
        .map((c) => ({ ...c, id: id(), target: a.id,
          day: c.day !== null && ["fixed_time", "time_window", "preferred_window", "unavailable"].includes(c.type) ? a.days[0] : c.day, source: "manual" })));
      try {
        if (problem.activities.length + copies.length > 100) throw new Error(`每份计划最多 100 项活动，当前最多还可添加 ${100 - problem.activities.length} 项，请减少日期或先删除活动。`);
        if (problem.constraints.length + constraints.length > 200) throw new Error("复制后约束将超过 200 条，请减少日期或先精简约束。");
        await onSave(copies, constraints);
      } catch (e) { setError((e as Error).message); }
      finally { setSaving(false); }
    }}>
      <p className="form-note">保留原活动，在所选日期各新增一项。{fixed ? "每项沿用原活动的固定开始时间。" : "每项由求解器在允许时间内独立安排。"}指定日期的单项时间限制会随复制日期移动；截止时间沿用本周原截止点，先后关系不会复制。</p>
      <div className="repeat-days">{DAYS.map((day, index) => <label key={day}><input type="checkbox" checked={days.includes(index)} disabled={saving}
        onChange={(e) => setDays(e.target.checked ? [...days, index].sort() : days.filter((d) => d !== index))}/>{day}</label>)}</div>
      {error && <div className="message error" role="alert">{error}</div>}
      <button className="primary" disabled={saving || !days.length}>{saving ? "正在保存…" : `新增 ${days.length} 项活动`}</button>
    </form>
  </Dialog>;
}
