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
import "./styles/editor-resource.css";

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
  const [saving, setSaving] = useState(false);
  const [validationError, setValidationError] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [name, setName] = useState(initial?.name ?? "");
  const [duration, setDuration] = useState(initial?.duration ?? 2);
  const [category, setCategory] = useState(initial?.category ?? {
    life: "study", academic: "course", lab: "experiment", meeting: "meeting", production: "operation",
  }[problem.scenario]);
  const [day, setDay] = useState(initialDay);
  const [start, setStart] = useState(
    fixedConstraint ? clock(fixedConstraint.start) : "19:00",
  );
  const [fixed, setFixed] = useState(Boolean(fixedConstraint));
  const [optional, setOptional] = useState(initial?.optional ?? false);
  const [resources, setResources] = useState<string[]>(initial?.resources ?? (
    problem.resources.find((resource) => resource.type !== "room")
      ? [problem.resources.find((resource) => resource.type !== "room")!.id] : []
  ));
  const [demands, setDemands] = useState<Record<string, number>>({ ...initial?.demands });
  const [rooms, setRooms] = useState<string[]>([...(initial?.room_options ?? [])]);
  const [requiredSeats, setRequiredSeats] = useState(initial?.required_seats ?? 0);
  const [roomType, setRoomType] = useState(initial?.room_type ?? "");
  const [customRoomType, setCustomRoomType] = useState(false);
  const [windowStart, setWindowStart] = useState(initial?.window_start ?? 16);
  const [windowEnd, setWindowEnd] = useState(initial?.window_end ?? 44);
  const [allowedDays, setAllowedDays] = useState<number[]>(initial?.days ?? (
    ["academic", "lab"].includes(problem.scenario) ? [0, 1, 2, 3, 4] : [0, 1, 2, 3, 4, 5, 6]
  ));
  const selectedResources = [...new Set([...resources, ...Object.keys(demands)])];
  const directResources = problem.resources.filter((resource) => resource.type !== "room" || selectedResources.includes(resource.id));
  const roomResources = problem.resources.filter((resource) => resource.type === "room" || rooms.includes(resource.id));
  const roomTypeNames: Record<string, string> = {
    lecture: "普通教室", computer: "计算机实验室", analysis: "分析实验室",
    general: "基础实验室", meeting: "普通会议室", video: "视频会议室",
  };
  const roomTypes = [...new Set([
    ...roomResources.map((resource) => resource.room_type), roomType,
  ])].filter(Boolean);
  const slotLabel = (slot: number) => slot === 48 ? "24:00" : clock(slot);
  function toggleResource(resourceId: string, checked: boolean) {
    setResources((current) => checked ? [...new Set([...current, resourceId])] : current.filter((value) => value !== resourceId));
    if (!checked) setDemands((current) => {
      const next = { ...current };
      delete next[resourceId];
      return next;
    });
    setValidationError("");
  }
  const categoryOptions = Array.from(
    new Set([...Object.keys(CATEGORIES), category]),
  );
  const durationOptions = Array.from(
    new Set([1, 2, 3, 4, 6, 8, 16, duration]),
  ).sort((a, b) => a - b);
  const initialDayLabel =
    allowedDays.length < 7 ? `所选日期内安排（共 ${allowedDays.length} 天）` : "本周任意一天";
  return (
    <Dialog title={initial ? "编辑活动" : "添加活动"} onClose={onClose} error={validationError || error}>
      <form noValidate
        onSubmit={async (e) => {
          e.preventDefault();
          if (saving) return;
          const aid = initial?.id ?? id();
          const cleanName = name.trim();
          const constraintDay = day === -1 ? 2 : day;
          const [h, m] = start.split(":").map(Number);
          let message = "";
          if (!cleanName) message = "请输入活动名称，不能只填写空格。";
          else if (day === -1 && !allowedDays.length) message = "请至少选择一个允许安排的日期。";
          else if (windowStart >= windowEnd || windowEnd - windowStart < duration) message = "允许时间范围需能容纳完整活动，请调整最早开始、最晚结束或时长。";
          else if (Object.values(demands).some((value) => !Number.isInteger(value) || value < 1 || value > 100)) message = "每项资源的需求数量需为 1 到 100 的整数。";
          else if (!Number.isInteger(requiredSeats) || requiredSeats < 0) message = "最低座位数需为大于或等于 0 的整数。";
          else if (!rooms.length && (requiredSeats > 0 || roomType.trim())) message = "设置了座位数或场地类型要求，请至少选择一个候选场地。";
          else if (fixed && (!Number.isInteger(h) || h < 0 || h > 23 || ![0, 30].includes(m))) message = "固定开始时间需以半小时为单位，例如 19:00 或 19:30。";
          else if (fixed && (h * 2 + m / 30 < windowStart || h * 2 + m / 30 + duration > windowEnd)) message = "固定开始时间与允许时间范围不一致，请在资源与时间设置中调整范围。";
          if (message) {
            setValidationError(message);
            if (cleanName) setSettingsOpen(true);
            return;
          }
          setValidationError("");
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
            resources,
            demands: { ...demands },
            room_options: rooms,
            required_seats: requiredSeats,
            room_type: roomType.trim(),
            days: day === -1 ? allowedDays : [day],
            window_start: windowStart,
            window_end: windowEnd,
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
          } catch (failure) {
            setValidationError(failure instanceof Error ? failure.message : "保存活动失败，请重试。");
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
            onChange={(e) => { setName(e.target.value); setValidationError(""); }}
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
              if (e.target.checked && !initial) { setWindowStart(0); setWindowEnd(48); }
              setValidationError("");
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
        <details className="editor-resource-settings" open={settingsOpen}
          onToggle={(event) => setSettingsOpen(event.currentTarget.open)}>
          <summary>资源与时间设置
            <small>{selectedResources.length} 项资源{rooms.length ? ` · ${rooms.length} 处候选场地` : ""} · {slotLabel(windowStart)}–{slotLabel(windowEnd)}</small>
          </summary>
          <div className="editor-resource-body">
            <fieldset className="editor-resource-group" disabled={saving}>
              <legend>同时占用的人员与设备</legend>
              <p>班级、教师和设备可同时选择；数量表示该活动同时需要几份。</p>
              {directResources.length === 0 && <p>暂无人员或设备，可在管理资源中新增。</p>}
              {directResources.map((resource) => {
                const checked = selectedResources.includes(resource.id);
                return <div className="editor-resource-choice" key={resource.id}>
                  <label><input type="checkbox" checked={checked}
                    aria-label={`占用${resource.name}`}
                    onChange={(event) => toggleResource(resource.id, event.target.checked)} />
                    <span>{resource.name}<small>可同时使用 {resource.capacity} 份</small></span>
                  </label>
                  {checked && <label className="editor-demand">
                    <span>数量</span><input type="number" min={1} max={100} step={1}
                      aria-label={`${resource.name}需求数量`}
                      value={Number.isNaN(demands[resource.id]) ? "" : demands[resource.id] ?? 1}
                      onChange={(event) => { setDemands((current) => ({ ...current, [resource.id]: event.target.valueAsNumber })); setValidationError(""); }} />
                  </label>}
                </div>;
              })}
            </fieldset>
            {roomResources.length > 0 && <fieldset className="editor-resource-group" disabled={saving}>
              <legend>候选场地</legend>
              <p>每次从所选场地中安排一处；不选则无需额外分配场地。</p>
              {roomResources.map((resource) => <label className="editor-room-choice" key={resource.id}>
                <input type="checkbox" aria-label={`候选场地${resource.name}`} checked={rooms.includes(resource.id)}
                  onChange={(event) => { setRooms((current) => event.target.checked ? [...current, resource.id] : current.filter((value) => value !== resource.id)); setValidationError(""); }} />
                <span>{resource.name}<small>{resource.seats} 座{resource.room_type ? ` · ${roomTypeNames[resource.room_type] ?? resource.room_type}` : ""}</small></span>
              </label>)}
              <div className="editor-resource-grid">
                <label>最低座位数
                  <input type="number" aria-label="最低座位数" min={0} step={1}
                    value={Number.isNaN(requiredSeats) ? "" : requiredSeats}
                    onChange={(event) => { setRequiredSeats(event.target.valueAsNumber); setValidationError(""); }} />
                </label>
                <label>场地类型要求
                  <select aria-label="场地类型要求" value={customRoomType ? "__custom__" : roomType}
                    onChange={(event) => {
                      setCustomRoomType(event.target.value === "__custom__");
                      if (event.target.value !== "__custom__") setRoomType(event.target.value);
                      setValidationError("");
                    }}>
                    <option value="">不限类型</option>
                    {roomTypes.map((value) => <option key={value} value={value}>{roomTypeNames[value] ?? value}</option>)}
                    <option value="__custom__">自定义类型</option>
                  </select>
                </label>
              </div>
              {customRoomType && <label className="editor-custom-room">自定义类型（与资源的场地类型一致）
                <input aria-label="自定义场地类型" maxLength={100} value={roomType}
                  onChange={(event) => { setRoomType(event.target.value); setValidationError(""); }} />
              </label>}
            </fieldset>}
            <fieldset className="editor-resource-group" disabled={saving}>
              <legend>允许时间范围</legend>
              <p>活动须完整落在此范围内；固定事项的开始时间也须符合范围。</p>
              <div className="editor-resource-grid">
                <label>最早开始
                  <select aria-label="最早开始" value={windowStart}
                    onChange={(event) => { setWindowStart(Number(event.target.value)); setValidationError(""); }}>
                    {Array.from({ length: 48 }, (_, slot) => <option value={slot} key={slot}>{slotLabel(slot)}</option>)}
                  </select>
                </label>
                <label>最晚结束
                  <select aria-label="最晚结束" value={windowEnd}
                    onChange={(event) => { setWindowEnd(Number(event.target.value)); setValidationError(""); }}>
                    {Array.from({ length: 48 }, (_, index) => index + 1).map((slot) => <option value={slot} key={slot}>{slotLabel(slot)}</option>)}
                  </select>
                </label>
              </div>
              {day === -1 && <div className="editor-day-options" role="group" aria-label="允许安排日期">
                {DAYS.map((label, value) => <label key={value}><input type="checkbox" checked={allowedDays.includes(value)}
                  aria-label={`允许${label}`}
                  onChange={(event) => { setAllowedDays((current) => event.target.checked ? [...current, value].sort((a, b) => a - b) : current.filter((entry) => entry !== value)); setValidationError(""); }} />{label}</label>)}
              </div>}
            </fieldset>
          </div>
        </details>
        <button type="submit" className="primary wide" disabled={saving}>
          {initial ? <Check size={16} /> : <Plus size={16} />}
          {saving ? "正在保存…" : initial ? "保存修改" : "添加并检查约束"}
        </button>
      </form>
    </Dialog>
  );
}
