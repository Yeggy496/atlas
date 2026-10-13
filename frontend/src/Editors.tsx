import { useState } from "react";
import { X, Check, Plus } from "lucide-react";
import {
  type Problem,
  type Constraint,
  type Activity,
  CATEGORIES,
  DAYS,
  clock,
  id,
} from "./types";

export function Dialog({
  title,
  onClose,
  children,
  error,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  error?: string;
}) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
        }}
      >
        <header>
          <h2>{title}</h2>
          <button
            autoFocus
            className="icon-button"
            onClick={onClose}
            aria-label="关闭"
          >
            <X size={20} />
          </button>
        </header>
        {error && <div className="message error dialog-error" role="alert">{error}</div>}
        {children}
      </section>
    </div>
  );
}

export function ConstraintEditor({
  problem,
  initial,
  onSave,
  onClose,
  error,
}: {
  problem: Problem;
  initial?: Constraint;
  onSave: (c: Constraint) => void | Promise<void>;
  onClose: () => void;
  error?: string;
}) {
  const [c, setC] = useState<Constraint>(
    initial ?? {
      id: id(),
      label: "",
      type: "unavailable",
      target: problem.resources[0]?.id ?? "*",
      level: "hard",
      day: 2,
      start: 28,
      end: 32,
      other: null,
      value: 1,
      source: "manual",
    },
  );
  const [saving, setSaving] = useState(false);
  const update = (key: string, value: unknown) => setC({ ...c, [key]: value });
  function changeType(type: Constraint["type"]) {
    const activityOnly = ["fixed_time", "precedence", "min_gap", "consecutive"].includes(type);
    setC({
      ...c, type, level: type === "preferred_window" ? "soft" : "hard",
      target: activityOnly && !problem.activities.some((a) => a.id === c.target)
        ? (problem.activities[0]?.id ?? "") : c.target,
      day: type === "fixed_time" ? (c.day ?? 0) : c.day,
      end: type === "deadline"
        ? Math.max(48, Math.min(336, Math.ceil(c.end / 48) * 48))
        : ["unavailable", "time_window", "preferred_window"].includes(type) ? Math.min(48, c.end) : c.end,
    });
  }
  return (
    <Dialog title={initial ? "编辑约束" : "添加约束"} onClose={onClose} error={error}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (saving) return;
          setSaving(true);
          try {
            await onSave({ ...c, label: c.label.trim() });
          } finally {
            setSaving(false);
          }
        }}
      >
        <label>
          约束说明
          <input
            required
            maxLength={160}
            value={c.label}
            onChange={(e) => update("label", e.target.value)}
            placeholder="例如：周三下午不可用"
          />
        </label>
        <div className="form-row">
          <label>
            约束类型
            <select
              aria-label="约束类型"
              value={c.type}
              onChange={(e) => changeType(e.target.value as Constraint["type"])}
            >
              <option value="unavailable">不可用时间</option>
              <option value="fixed_time">固定开始时间</option>
              <option value="time_window">允许时间窗口</option>
              <option value="preferred_window">偏好时间窗口</option>
              <option value="daily_limit">每日次数上限</option>
              <option value="deadline">截止时间</option>
              <option value="precedence">前置关系</option>
              <option value="min_gap">最小时间间隔</option>
              <option value="consecutive">连排（紧接下一活动）</option>
            </select>
          </label>
          <label>
            作用对象
            <select
              aria-label="作用对象"
              value={c.target}
              onChange={(e) => setC({ ...c, target: e.target.value, other: c.other === e.target.value ? null : c.other })}
              required
            >
              {!["fixed_time", "precedence", "min_gap", "consecutive"].includes(
                c.type,
              ) && (
                <>
                  <option value="*">全部活动</option>
                  <optgroup label="资源">
                    {problem.resources.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.name}
                      </option>
                    ))}
                  </optgroup>
                  <optgroup label="活动类别">
                    {Array.from(
                      new Set(problem.activities.map((a) => a.category)),
                    ).map((cat) => (
                      <option value={cat} key={cat}>
                      {CATEGORIES[cat]?.label ?? cat}
                      </option>
                    ))}
                  </optgroup>
                </>
              )}
              <optgroup label="具体活动">
                {problem.activities.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>
        </div>
        {[
          "unavailable",
          "fixed_time",
          "time_window",
          "preferred_window",
        ].includes(c.type) && (
          <>
            <label>
              日期
              <select
                aria-label="日期"
                value={c.day ?? -1}
                onChange={(e) =>
                  update(
                    "day",
                    Number(e.target.value) === -1
                      ? null
                      : Number(e.target.value),
                  )
                }
              >
                {c.type !== "fixed_time" && <option value={-1}>每天</option>}
                {DAYS.map((d, i) => (
                  <option key={d} value={i}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <div className="form-row">
              <label>
                开始时间
                <input
                  type="time"
                  step="1800"
                  required
                  value={`${String(Math.floor(c.start / 2)).padStart(2, "0")}:${c.start % 2 ? "30" : "00"}`}
                  onChange={(e) => {
                    const [h, m] = e.target.value.split(":").map(Number);
                    update("start", h * 2 + m / 30);
                  }}
                />
              </label>
              {c.type !== "fixed_time" && (
                <label>
                  结束时间
                  <select
                    aria-label="结束时间"
                    value={c.end}
                    onChange={(e) => update("end", Number(e.target.value))}
                  >
                    {Array.from({ length: 48 }, (_, i) => i + 1).map((s) => (
                      <option key={s} value={s}>
                        {String(Math.floor(s / 2)).padStart(2, "0")}:
                        {s % 2 ? "30" : "00"}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </>
        )}
        {c.type === "deadline" && (
          <label>
            截止到
            <select
              aria-label="截止到"
              value={c.end}
              onChange={(e) => update("end", Number(e.target.value))}
            >
              {(c.end === 0 || c.end % 48 !== 0) && (
                <option value={c.end}>
                  {DAYS[Math.floor(c.end / 48)]} {clock(c.end)}
                </option>
              )}
              {DAYS.map((d, i) => (
                <option value={(i + 1) * 48} key={d}>
                  {d} 24:00
                </option>
              ))}
            </select>
          </label>
        )}
        {["precedence", "min_gap", "consecutive"].includes(c.type) && (
          <label>
            后续活动
            <select
              aria-label="后续活动"
              required
              value={c.other ?? ""}
              onChange={(e) => update("other", e.target.value)}
            >
              <option value="">请选择</option>
              {problem.activities
                .filter((a) => a.id !== c.target)
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
            </select>
          </label>
        )}
        {["daily_limit", "min_gap"].includes(c.type) && (
          <label>
            {c.type === "daily_limit" ? "每天最多次数" : "间隔（30 分钟单位）"}
            <input
              type="number"
              min="0"
              max="100"
              value={c.value}
              onChange={(e) => update("value", Number(e.target.value))}
            />
          </label>
        )}
        <div className="form-note">
          {c.level === "soft"
            ? "软约束：尽量满足，无法满足时会产生惩罚。"
            : "硬约束：必须满足，否则不返回合法计划。"}
        </div>
        <button type="submit" className="primary wide" disabled={saving}>
          <Check size={16} />
          {saving ? "正在保存…" : "保存约束"}
        </button>
      </form>
    </Dialog>
  );
}

export function ActivityEditor({
  problem,
  initial,
  onSave,
  onClose,
  error,
}: {
  problem: Problem;
  initial?: Activity;
  onSave: (a: Activity, c?: Constraint) => void | Promise<void>;
  onClose: () => void;
  error?: string;
}) {
  const fixedConstraint = initial
    ? problem.constraints.find(
        (c) => c.type === "fixed_time" && c.target === initial.id,
      )
    : undefined;
  const initialDay =
    fixedConstraint?.day ?? (initial?.days.length === 1 ? initial.days[0] : -1);
  const initialResources = initial?.resources ?? [];
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState(initial?.name ?? "");
  const [duration, setDuration] = useState(initial?.duration ?? 2);
  const [category, setCategory] = useState(initial?.category ?? "study");
  const [day, setDay] = useState(initialDay);
  const [start, setStart] = useState(
    fixedConstraint ? clock(fixedConstraint.start) : "19:00",
  );
  const [fixed, setFixed] = useState(Boolean(fixedConstraint));
  const [optional, setOptional] = useState(initial?.optional ?? false);
  const [resource, setResource] = useState(
    initial
      ? initialResources.length === 1
        ? initialResources[0]
        : ""
      : (problem.resources[0]?.id ?? ""),
  );
  const categoryOptions = Array.from(
    new Set([...Object.keys(CATEGORIES), category]),
  );
  const durationOptions = Array.from(
    new Set([1, 2, 3, 4, 6, 8, 16, duration]),
  ).sort((a, b) => a - b);
  const initialDayLabel =
    initial && initial.days.length > 1 && initial.days.length < 7
      ? `保留原有日期（共 ${initial.days.length} 天）`
      : "本周任意一天";
  return (
    <Dialog title={initial ? "编辑活动" : "添加活动"} onClose={onClose} error={error}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (saving) return;
          const aid = initial?.id ?? id();
          const cleanName = name.trim();
          const constraintDay = day === -1 ? 2 : day;
          const [h, m] = start.split(":").map(Number);
          const a: Activity = {
            ...(initial ?? {
              id: aid,
              demands: {},
              room_options: [],
              required_seats: 0,
              room_type: "",
              priority: 5,
              group: null,
              op_index: 0,
            }),
            id: aid,
            name: cleanName,
            duration,
            category,
            resources:
              initial && resource === ""
                ? initial.resources
                : resource
                  ? [resource]
                  : [],
            days:
              day === -1
                ? initial && initial.days.length > 1
                  ? initial.days
                  : [0, 1, 2, 3, 4, 5, 6]
                : [day],
            window_start: fixed ? 0 : (initial?.window_start ?? 16),
            window_end: fixed ? 48 : (initial?.window_end ?? 44),
            optional,
          };
          setSaving(true);
          try {
            await onSave(
            a,
            fixed
              ? {
                  ...(fixedConstraint ?? {}),
                  id: fixedConstraint?.id ?? id(),
                  label: `${cleanName} · ${DAYS[constraintDay]} ${start} 固定开始`,
                  type: "fixed_time",
                  target: aid,
                  level: "hard",
                  day: constraintDay,
                  start: h * 2 + Math.floor(m / 30),
                  end: 48,
                  other: null,
                  value: 0,
                  source: fixedConstraint?.source ?? "manual",
                }
              : undefined,
            );
          } finally {
            setSaving(false);
          }
        }}
      >
        <label>
          活动名称
          <input
            required
            maxLength={100}
            autoFocus
            placeholder="例如：社团会议、课程复习"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <div className="form-row">
          <label>
            时长
            <select
              aria-label="时长"
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
            >
              {durationOptions.map((x) => (
                <option key={x} value={x}>
                  {x / 2} 小时
                </option>
              ))}
            </select>
          </label>
          <label>
            类别
            <select
              aria-label="类别"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {categoryOptions.map((value) => (
                <option key={value} value={value}>
                  {CATEGORIES[value]?.label ?? value}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label>
          占用资源
          <select
            aria-label="占用资源"
            value={resource}
            onChange={(e) => setResource(e.target.value)}
          >
            {initial && (
              <option value="">
                {initialResources.length > 1
                  ? `保留原有资源（共 ${initialResources.length} 项）`
                  : "无固定资源"}
              </option>
            )}
            {problem.resources.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          日期
          <select aria-label="日期" value={day} onChange={(e) => setDay(Number(e.target.value))}>
            {!fixed && <option value={-1}>{initialDayLabel}</option>}
            {DAYS.map((d, i) => (
              <option key={d} value={i}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label className="check-label">
          <input
            type="checkbox"
            checked={fixed}
            onChange={(e) => {
              setFixed(e.target.checked);
              if (e.target.checked && day === -1) setDay(2);
            }}
          />
          固定开始时间
        </label>
        {fixed && (
          <label>
            开始时间
            <input
              required
              type="time"
              step="1800"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </label>
        )}
        <label className="check-label">
          <input
            type="checkbox"
            checked={optional}
            onChange={(e) => setOptional(e.target.checked)}
          />
          可选活动，允许时间不足时不安排
        </label>
        <button type="submit" className="primary wide" disabled={saving}>
          {initial ? <Check size={16} /> : <Plus size={16} />}
          {saving ? "正在保存…" : initial ? "保存修改" : "添加并检查约束"}
        </button>
      </form>
    </Dialog>
  );
}
