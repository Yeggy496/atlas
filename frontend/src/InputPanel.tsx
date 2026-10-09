import { type RefObject } from "react";
import {
  Sparkles,
  ArrowRight,
  Loader2,
  Upload,
  Download,
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
} from "lucide-react";
import {
  type Problem,
  type Constraint,
  type Activity,
  type Mode,
  type Scenario,
  type Assignment,
  CATEGORIES,
} from "./types";
interface Props {
  problem: Problem | null;
  busy: string;
  provider: string;
  input: string;
  setInput: (v: string) => void;
  parse: () => Promise<void>;
  scenario: Scenario;
  summary: string[];
  warnings: string[];
  inputTab: "constraints" | "activities";
  setInputTab: (v: "constraints" | "activities") => void;
  setConstraintEditor: (v: Constraint | "new" | null) => void;
  deleteConstraint: (v: Constraint) => void;
  deleteActivity: (v: Activity) => void;
  mode: Mode;
  setMode: (v: Mode) => void;
  setHelp: (v: boolean) => void;
  reviewed: boolean;
  setReviewed: (v: boolean) => void;
  optimize: () => Promise<void>;
  previous: RefObject<Assignment[]>;
  fileRef: RefObject<HTMLInputElement | null>;
  importFile: (f: File) => Promise<void>;
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
  parse,
  scenario,
  summary,
  warnings,
  inputTab,
  setInputTab,
  setConstraintEditor,
  deleteConstraint,
  deleteActivity,
  mode,
  setMode,
  setHelp,
  reviewed,
  setReviewed,
  optimize,
  previous,
  fileRef,
  importFile,
}: Props) {
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
          {provider === "demo" ? "离线演示" : "LLM"}
        </span>
      </div>
      <div className="nl-input">
        <textarea
          aria-label="自然语言需求"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="例如：周三19:00有一个临时会议。"
          disabled={!!busy}
        />
        <div>
          <span>
            <Sparkles size={12} />
            {provider === "demo" ? "支持示例句式" : "结构化约束解析"}
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
            识别约束
          </button>
        </div>
      </div>
      <div className="import-row">
        <button disabled={!!busy} onClick={() => fileRef.current?.click()}>
          <Upload size={14} />
          导入 CSV / XLSX
        </button>
        <a href={`/api/import/template.csv?scenario=${scenario}`} download>
          <Download size={13} />
          模板
        </a>
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.xlsx"
          hidden
          onChange={(e) => {
            if (e.target.files?.[0]) void importFile(e.target.files[0]);
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
      <div className="constraint-list">
        {inputTab === "constraints"
          ? problem?.constraints.map((c) => (
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
                  <p>{c.label}</p>
                  <small>
                    {c.level === "hard" ? "硬约束" : "软偏好"}
                    <span>·</span>
                    {c.source === "template"
                      ? "示例"
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
          : problem?.activities.map((a) => (
              <article className="activity-row" key={a.id}>
                <span
                  className={`dot ${(CATEGORIES[a.category] ?? CATEGORIES.study).color}`}
                />
                <div>
                  <strong>{a.name}</strong>
                  <small>
                    {a.duration / 2} 小时 · {a.optional ? "可选" : "必须完成"}
                  </small>
                </div>
                <button
                  className="icon-button"
                  aria-label={`删除活动 ${a.name}`}
                  disabled={!!busy}
                  onClick={() => deleteActivity(a)}
                >
                  <Trash2 size={13} />
                </button>
              </article>
            ))}
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
              onClick={() => setMode(m.id)}
              className={mode === m.id ? "active" : ""}
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
        </p>
        <label className="review-check">
          <input
            type="checkbox"
            checked={reviewed}
            disabled={!!busy}
            onChange={(e) => setReviewed(e.target.checked)}
          />
          <span>我已检查并确认当前任务与约束</span>
        </label>
        <button
          className="optimize-button"
          onClick={optimize}
          disabled={!!busy || !reviewed || !problem}
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
