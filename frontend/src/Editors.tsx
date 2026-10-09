import { useState } from "react";
import { X, Check, Plus } from "lucide-react";
import {
  type Problem,
  type Constraint,
  type Activity,
  DAYS,
  id,
} from "./types";

export function Dialog({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
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
}: {
  problem: Problem;
  initial?: Constraint;
  onSave: (c: Constraint) => void;
  onClose: () => void;
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
  const update = (key: string, value: unknown) => setC({ ...c, [key]: value });
  return (
    <Dialog title={initial ? "编辑约束" : "添加约束"} onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave(c);
        }}
      >
        <label>
          约束说明
          <input
            required
            value={c.label}
            onChange={(e) => update("label", e.target.value)}
            placeholder="例如：周三下午不可用"
          />
        </label>
        <div className="form-row">
          <label>
            约束类型
            <select
              value={c.type}
              onChange={(e) =>
                setC({
                  ...c,
                  type: e.target.value as Constraint["type"],
                  level:
                    e.target.value === "preferred_window" ? "soft" : "hard",
                  target:
                    e.target.value === "fixed_time"
                      ? (problem.activities[0]?.id ?? "")
                      : c.target,
                })
              }
            >
              <option value="unavailable">不可用时间</option>
              <option value="fixed_time">固定开始时间</option>
              <option value="time_window">允许时间窗口</option>
              <option value="preferred_window">偏好时间窗口</option>
              <option value="daily_limit">每日次数上限</option>
              <option value="deadline">截止时间</option>
              <option value="precedence">前置关系</option>
              <option value="min_gap">最小时间间隔</option>
            </select>
          </label>
          <label>
            作用对象
            <select
              value={c.target}
              onChange={(e) => update("target", e.target.value)}
            >
              {!["fixed_time", "precedence", "min_gap"].includes(c.type) && (
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
                        {cat}
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
              value={c.end}
              onChange={(e) => update("end", Number(e.target.value))}
            >
              {DAYS.map((d, i) => (
                <option value={(i + 1) * 48} key={d}>
                  {d} 24:00
                </option>
              ))}
            </select>
          </label>
        )}
        {["precedence", "min_gap"].includes(c.type) && (
          <label>
            后续活动
            <select
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
        <button type="submit" className="primary wide">
          <Check size={16} />
          保存约束
        </button>
      </form>
    </Dialog>
  );
}

export function ActivityEditor({
  problem,
  onSave,
  onClose,
}: {
  problem: Problem;
  onSave: (a: Activity, c?: Constraint) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const [duration, setDuration] = useState(2);
  const [category, setCategory] = useState("study");
  const [day, setDay] = useState(-1);
  const [start, setStart] = useState("19:00");
  const [fixed, setFixed] = useState(false);
  const [optional, setOptional] = useState(false);
  const [resource, setResource] = useState(problem.resources[0]?.id ?? "");
  return (
    <Dialog title="添加活动" onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const aid = id();
          const a: Activity = {
            id: aid,
            name,
            duration,
            category,
            resources: [resource],
            demands: {},
            room_options: [],
            required_seats: 0,
            room_type: "",
            days: day === -1 ? [0, 1, 2, 3, 4, 5, 6] : [day],
            window_start: fixed ? 0 : 16,
            window_end: fixed ? 48 : 44,
            optional,
            priority: 5,
          };
          const [h, m] = start.split(":").map(Number);
          onSave(
            a,
            fixed
              ? {
                  id: id(),
                  label: `${name} · ${DAYS[day]} ${start} 固定开始`,
                  type: "fixed_time",
                  target: aid,
                  level: "hard",
                  day,
                  start: h * 2 + m / 30,
                  end: 48,
                  other: null,
                  value: 0,
                  source: "manual",
                }
              : undefined,
          );
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
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
            >
              {[1, 2, 3, 4, 6, 8, 16].map((x) => (
                <option key={x} value={x}>
                  {x / 2} 小时
                </option>
              ))}
            </select>
          </label>
          <label>
            类别
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              <option value="study">学习</option>
              <option value="homework">作业</option>
              <option value="meeting">会议</option>
              <option value="exercise">运动</option>
              <option value="course">课程</option>
              <option value="experiment">实验</option>
              <option value="leisure">自由活动</option>
            </select>
          </label>
        </div>
        <label>
          占用资源
          <select
            value={resource}
            onChange={(e) => setResource(e.target.value)}
          >
            {problem.resources.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          日期
          <select value={day} onChange={(e) => setDay(Number(e.target.value))}>
            {!fixed && <option value={-1}>本周任意一天</option>}
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
        <button type="submit" className="primary wide">
          <Plus size={16} />
          添加并检查约束
        </button>
      </form>
    </Dialog>
  );
}
