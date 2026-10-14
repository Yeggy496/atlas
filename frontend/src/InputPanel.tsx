import { useRef, useState, type RefObject } from "react";
import { describeConstraint } from "./constraintDescription";
import {
  Sparkles,
  ArrowRight,
  Loader2,
  Upload,
  Download,
  FileText,
  CheckCheck,
  Plus,
  LockKeyhole,
  Pencil,
  X,
  Trash2,
  SlidersHorizontal,
  CircleHelp,
  Play,
  ShieldCheck,
  Zap,
  Copy,
} from "lucide-react";
import {
  type Problem,
  type Constraint,
  type Activity,
  type Mode,
  type Scenario,
  type Assignment,
  type WeightsMeta,
  CATEGORIES,
} from "./types";
import { WeightPanel } from "./WeightPanel";
import { MAX_INPUT_CHARS } from "./types";
interface Props {
  problem: Problem | null;
  busy: string;
  provider: string;
  input: string;
  setInput: (v: string) => void;
  inputPending: boolean;
  acknowledgeInput: () => void;
  clearInput: () => void;
  repeatActivity: (v: Activity) => void;
  downloadTemplate: () => void;
  scheduledIds: Set<string> | null;
  weightsFailed: boolean;
  retryConnection: () => void;
  clearContent: () => void;
  clearConstraints: () => void;
  clearActivities: () => void;
  parse: () => Promise<void>;
  scenario: Scenario;
  summary: string[];
  warnings: string[];
  inputTab: "constraints" | "activities";
  setInputTab: (v: "constraints" | "activities") => void;
  setConstraintEditor: (v: Constraint | "new" | null) => void;
  deleteConstraint: (v: Constraint) => void;
  deleteActivity: (v: Activity) => void;
  editActivity: (v: Activity) => void;
  mode: Mode;
  setMode: (v: Mode) => void;
  weightsMeta: WeightsMeta | null;
  customWeights: Record<string, number> | null;
  appliedWeights: Record<string, number> | null;
  setCustomWeights: (v: Record<string, number> | null) => void;
  setHelp: (v: boolean) => void;
  reviewed: boolean;
  setReviewed: (v: boolean) => void;
  optimize: (
    modeOverride?: Mode,
    fresh?: boolean,
    weightsOverride?: Record<string, number> | null,
  ) => Promise<void>;
  previous: RefObject<Assignment[]>;
  fileRef: RefObject<HTMLInputElement | null>;
  importFile: (f: File) => Promise<void>;
  textFileRef: RefObject<HTMLInputElement | null>;
  importText: (f: File) => Promise<void>;
}
const MODES: { id: Mode; label: string; icon: typeof Zap }[] = [
  { id: "efficient", label: "高效", icon: Zap },
  { id: "balanced", label: "均衡", icon: SlidersHorizontal },
  { id: "robust", label: "稳健", icon: ShieldCheck },
];

export function InputPanel({
  problem,
  busy,
  provider,
  input,
  setInput,
  inputPending, acknowledgeInput, clearInput, repeatActivity, downloadTemplate, scheduledIds, weightsFailed, retryConnection,
  clearContent,
  clearConstraints,
  clearActivities,
  parse,
  scenario,
  summary,
  warnings,
  inputTab,
  setInputTab,
  setConstraintEditor,
  deleteConstraint,
  deleteActivity,
  editActivity,
  mode,
  setMode,
  weightsMeta,
  customWeights,
  appliedWeights,
  setCustomWeights,
  setHelp,
  reviewed,
  setReviewed,
  optimize,
  previous,
  fileRef,
  importFile,
  textFileRef,
  importText,
}: Props) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const inputTooLong = input.length > MAX_INPUT_CHARS;
  const activityGroups = new Map<string, Activity[]>();
  for (const a of problem?.activities ?? []) {
    if (a.group) {
      const list = activityGroups.get(a.group) ?? [];
      list.push(a);
      activityGroups.set(a.group, list);
    }
  }
  activityGroups.forEach((list) => list.sort((x, y) => x.op_index - y.op_index));
  const renderedGroups = new Set<string>();
  return (
    <aside className="input-panel panel">
      <div className="input-panel-header">
        <span className="section-icon">
          <Sparkles size={18} />
        </span>
        <div>
          <h2>描述你的安排</h2>
          <p>需求从这里开始</p>
        </div>
        <span className="ai-tag">
          {provider === "demo" ? "规则解析" : provider === "deepseek" ? "DeepSeek" : "OpenAI"}
        </span>
      </div>
      <div className="nl-input">
        <textarea
          ref={inputRef}
          aria-label="自然语言需求"
          aria-describedby="input-length-hint"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="例如：周三19:00有一个临时会议。"
          disabled={!!busy}
        />
        <div>
          <span>
            <Sparkles size={12} />
            {provider === "demo" ? "按规则识别需求" : "AI 识别任务与约束"}
          </span>
          <button
            className="parse-button"
            disabled={!!busy || !input.trim() || !problem}
            onClick={parse}
          >
            {busy === "正在识别约束" ? (
              <Loader2 size={14} className="spin" />
            ) : (
              <ArrowRight size={14} />
            )}
            {inputTooLong ? "识别下一段" : "识别约束"}
          </button>
        </div>
      </div>
      <div className="input-meta">
        <div className="input-clear-actions">
        <button
          type="button"
          className="clear-input-button"
          disabled={!!busy || input.length === 0}
          onClick={() => { clearInput(); inputRef.current?.focus(); }}
          title="清空输入文字"
        >
          <X size={12} />
          清空输入
        </button>
        <button
          type="button"
          className="clear-input-button clear-content-button"
          disabled={!!busy || !problem || !(input.length || problem.activities.length || problem.constraints.length || summary.length || warnings.length)}
          onClick={clearContent}
          title="清空当前场景的输入、活动与约束"
        >
          <Trash2 size={12} />
          清空当前内容
        </button>
        </div>
        <p id="input-length-hint" className={`input-length-hint ${inputTooLong ? "too-long" : ""}`}>
          {inputTooLong ? `剩余 ${input.length.toLocaleString()} 字 · 每次识别最多 4,000 字，余下文字会保留` : `${input.length.toLocaleString()} / 4,000 字`}
        </p>
      </div>
      {inputPending && <div className="pending-input" role="status">
        <strong>这段需求尚未纳入计划</strong><p>先点击“{inputTooLong ? "识别下一段" : "识别约束"}”，再检查新增或修改的内容。</p>
        <button disabled={!!busy} onClick={acknowledgeInput}>本次仅使用现有任务与约束</button>
      </div>}
      <div className="import-row">
        <button disabled={!!busy} onClick={() => fileRef.current?.click()}>
          <Upload size={14} />
          导入 CSV / XLSX
        </button>
        <button
          disabled={!!busy}
          onClick={() => textFileRef.current?.click()}
          title="导入 TXT / PDF 文本，自动识别其中的需求"
        >
          <FileText size={14} />
          TXT / PDF
        </button>
        <button disabled={!!busy || !problem} onClick={downloadTemplate} title="下载含当前资源名称的任务模板，导入会追加活动">
          <Download size={13} />
          模板
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.xlsx"
          hidden
          onChange={(e) => {
            if (e.target.files?.[0]) void importFile(e.target.files[0]);
          }}
        />
        <input
          ref={textFileRef}
          type="file"
          accept=".txt,.pdf"
          hidden
          onChange={(e) => {
            if (e.target.files?.[0]) void importText(e.target.files[0]);
          }}
        />
      </div>
      {summary.length > 0 && (
        <details className="parse-summary" open>
          <summary>
            <CheckCheck size={15} />
            本次识别 / 导入结果
          </summary>
          {summary.map((s, i) => (
            <p key={i}>{s}</p>
          ))}
        </details>
      )}
      {warnings.length > 0 && (
        <div className="parse-warning" role="status">
          {warnings.map((w, i) => (
            <p key={i}>{w}</p>
          ))}
        </div>
      )}
      <div className="input-tabs">
        <button
          className={inputTab === "constraints" ? "active" : ""}
          onClick={() => setInputTab("constraints")}
        >
          约束 <span>{problem?.constraints.length ?? 0}</span>
        </button>
        <button
          className={inputTab === "activities" ? "active" : ""}
          onClick={() => setInputTab("activities")}
        >
          活动 <span>{problem?.activities.length ?? 0}</span>
        </button>
        <button
          className="icon-button"
          title="添加约束"
          aria-label="添加约束"
          disabled={!!busy || !problem}
          onClick={() => setConstraintEditor("new")}
        >
          <Plus size={16} />
        </button>
      </div>
      <div className="collection-tools">
        <input aria-label="搜索活动或约束" placeholder="搜索名称、资源或条件" value={query} onChange={(e) => setQuery(e.target.value)}/>
        {inputTab === "activities" && <select aria-label="筛选活动" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">全部活动</option><option value="required">必做活动</option><option value="optional">可选活动</option>
          {scheduledIds && <><option value="scheduled">已安排</option><option value="unassigned">未安排</option></>}
        </select>}
        <button
          type="button"
          disabled={!!busy || !problem || !(inputTab === "constraints" ? problem.constraints.length : problem.activities.length)}
          onClick={inputTab === "constraints" ? clearConstraints : clearActivities}
        >
          <Trash2 size={12}/>
          {inputTab === "constraints" ? "清空约束" : "清空活动"}
        </button>
      </div>
      <div className="constraint-list">
        {problem && !problem.activities.length && <div className="start-plan-note">
          还没有活动。点击上方“添加活动”，或描述本周需求后点击“识别约束”。
        </div>}
        {inputTab === "constraints"
          ? problem?.constraints.filter((c) => `${c.label} ${describeConstraint(c, problem)}`.toLowerCase().includes(query.toLowerCase())).map((c) => (
              <article className="constraint-card" key={c.id}>
                <span
                  className={`constraint-symbol ${c.level === "soft" ? "soft" : ""}`}
                >
                  {c.level === "hard" ? (
                    <LockKeyhole size={13} />
                  ) : (
                    <Sparkles size={13} />
                  )}
                </span>
                <div>
                  <p>{describeConstraint(c, problem)}</p>
                  {c.label !== describeConstraint(c, problem) && <p className="constraint-facts">备注：{c.label}</p>}
                  <small>
                    {c.level === "hard" ? "硬约束" : "软偏好"}
                    <span>·</span>
                    {c.source === "template"
                      ? "预置"
                      : c.source === "file"
                        ? "文件导入"
                        : "用户输入"}
                  </small>
                </div>
                <div className="card-actions">
                  <button
                    aria-label={`编辑 ${c.label}`}
                    disabled={!!busy}
                    onClick={() => setConstraintEditor(c)}
                  >
                    <Pencil size={12} />
                  </button>
                  <button
                    aria-label={`删除 ${c.label}`}
                    disabled={!!busy}
                    onClick={() => deleteConstraint(c)}
                  >
                    <X size={13} />
                  </button>
                </div>
              </article>
            ))
          : problem?.activities.map((a) => {
              if (!`${a.name} ${a.resources.map((id) => problem.resources.find((r) => r.id === id)?.name ?? "").join(" ")}`.toLowerCase().includes(query.toLowerCase()) ||
                filter === "required" && a.optional || filter === "optional" && !a.optional ||
                filter === "scheduled" && scheduledIds && !scheduledIds.has(a.id) || filter === "unassigned" && scheduledIds?.has(a.id)) return null;
              if (a.group) {
                if (renderedGroups.has(a.group)) return null;
                renderedGroups.add(a.group);
                const steps = activityGroups.get(a.group) ?? [a];
                return (
                  <article
                    className="activity-row activity-group"
                    key={a.group}
                  >
                    <span
                      className={`dot ${(CATEGORIES.operation ?? CATEGORIES.study).color}`}
                    />
                    <div>
                      <strong>{a.name.split(" · ").slice(0, 2).join(" · ")}</strong>
                      <small>
                        {steps.length} 道工序 ·{" "}
                        {steps
                          .map((s) => s.name.split(" · ").pop())
                          .join(" → ")}
                      </small>
                    </div>
                    <button
                      className="icon-button"
                      aria-label={`删除工单 ${a.name}`}
                      disabled={!!busy}
                      onClick={() => steps.forEach(deleteActivity)}
                    >
                      <Trash2 size={13} />
                    </button>
                  </article>
                );
              }
              return (
                <article className="activity-row" key={a.id}>
                  <span
                    className={`dot ${(CATEGORIES[a.category] ?? CATEGORIES.study).color}`}
                  />
                  <div>
                    <strong>{a.name}</strong>
                    <small>
                      {a.duration / 2} 小时 ·{" "}
                      {a.optional ? "可选" : "必须完成"}
                    </small>
                  </div>
                  <button
                    className="icon-button" aria-label={`重复活动 ${a.name}`} title="复制到多个日期" disabled={!!busy} onClick={() => repeatActivity(a)}
                  ><Copy size={13}/></button>
                  <button
                    className="icon-button"
                    aria-label={`编辑活动 ${a.name}`}
                    disabled={!!busy}
                    onClick={() => editActivity(a)}
                  >
                    <Pencil size={13} />
                  </button>
                  <button
                    className="icon-button"
                    aria-label={`删除活动 ${a.name}`}
                    disabled={!!busy}
                    onClick={() => deleteActivity(a)}
                  >
                    <Trash2 size={13} />
                  </button>
                </article>
              );
            })}
      </div>
      <div className="optimization-controls">
        <div className="controls-title">
          <SlidersHorizontal size={15} />
          <strong>优化偏好</strong>
          <button
            aria-label="查看优化指标说明"
            className="icon-button"
            onClick={() => setHelp(true)}
          >
            <CircleHelp size={13} />
          </button>
        </div>
        <div className="mode-selector">
          {MODES.map((m) => (
            <button
              key={m.id}
              disabled={!!busy}
              onClick={() => {
                setMode(m.id);
                // Switching a preset drops any custom profile. The cleared profile
                // must be passed explicitly because setCustomWeights is async and
                // optimize() would otherwise still see the previous custom weights.
                setCustomWeights(null);
                void optimize(m.id, false, null);
              }}
              className={mode === m.id && !customWeights ? "active" : ""}
            >
              <m.icon size={13} />
              {m.label}
            </button>
          ))}
        </div>
        <p>
          {mode === "efficient"
            ? "优先满足目标，减少空档时间。"
            : mode === "balanced"
              ? "兼顾目标、时间紧凑与每日负载。"
              : "优先保留已有安排，并提前完成截止任务。"}
          <span className="mode-hint">{reviewed && !inputPending ? "切换档位会立即按新偏好重新求解" : "识别需求并确认约束后，按所选偏好生成计划"}</span>
          {mode !== "robust" && <span className="mode-hint">需要尽量保留原安排时，可选择稳健模式。</span>}
        </p>
        <details className="advanced-weights"><summary>自定义优化权重</summary>
        {weightsFailed ? <p className="weight-empty">权重配置读取失败。<button disabled={!!busy} onClick={retryConnection}>重试</button></p> : <WeightPanel
          meta={weightsMeta}
          mode={mode}
          weights={customWeights}
          appliedWeights={appliedWeights}
          reviewed={reviewed && !inputPending && !!problem?.activities.length}
          busy={!!busy}
          onChange={setCustomWeights}
          onApply={(override) =>
            void optimize(mode, false, override === undefined ? customWeights : override)
          }
        />}</details>
        <label className="review-check">
          <input
            type="checkbox"
            checked={reviewed}
            disabled={!!busy || inputPending}
            onChange={(e) => setReviewed(e.target.checked)}
          />
          <span>我已检查并确认当前任务与约束</span>
        </label>
        <button
          className="optimize-button"
          onClick={() => void optimize()}
          disabled={!!busy || inputPending || !reviewed || !problem?.activities.length}
        >
          {busy ? (
            <>
              <Loader2 size={17} className="spin" />
              {busy}
            </>
          ) : (
            <>
              <Play size={16} fill="currentColor" />
              {previous.current.length ? "重新优化" : "生成计划"}
              <span>Optimize</span>
            </>
          )}
        </button>
        <div className="provider-note">
          <ShieldCheck size={11} />
          理解与求解分离 · 结果经独立校验
        </div>
      </div>
    </aside>
  );
}
