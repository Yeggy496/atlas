import { InputPanel } from "./InputPanel";
import { ResultPanel } from "./ResultPanel";
import { useEffect, useRef, useState } from "react";
import {
  Activity as ActivityIcon,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Factory,
  FlaskConical,
  GraduationCap,
  History,
  Layers3,
  LayoutDashboard,
  Loader2,
  LockKeyhole,
  PanelLeftClose,
  Pencil,
  Play,
  Plus,
  RotateCcw,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Upload,
  UserRound,
  Users,
  Workflow,
  X,
  Zap,
  AlertTriangle,
  Download,
  CheckCircle2,
} from "lucide-react";
import { api, exportPlan as exportPlanRequest, readResponse } from "./api";
import { Calendar } from "./Calendar";
import { ActivityEditor, ConstraintEditor, Dialog } from "./Editors";
import {
  type Activity,
  type Assignment,
  type Constraint,
  type Explanation,
  type HistoryRun,
  type Mode,
  type Problem,
  type Result,
  type Scenario,
  type WeightsMeta,
  CATEGORIES,
  DAYS,
  SCENARIOS,
  clock,
  MAX_INPUT_CHARS,
} from "./types";

const SCENARIO_ICONS: Record<Scenario, typeof CalendarDays> = {
  life: CalendarDays,
  academic: GraduationCap,
  lab: FlaskConical,
  meeting: Users,
  production: Factory,
};

export default function App() {
  const [problem, setProblem] = useState<Problem | null>(null),
    [result, setResult] = useState<Result | null>(null);
  const [scenario, setScenario] = useState<Scenario>("life"),
    [mode, setMode] = useState<Mode>("balanced");
  // Custom weight profile (MASTER_SPEC §15). null means "use the preset as-is";
  // the slider panel populates it when the user switches to 自定义.
  const [customWeights, setCustomWeights] = useState<Record<string, number> | null>(
      null,
    ),
    [weightsMeta, setWeightsMeta] = useState<WeightsMeta | null>(null);
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [input, setInput] = useState(SCENARIOS.life.input),
    [provider, setProvider] = useState("demo");
  const [version, setVersion] = useState("");
  const [reviewed, setReviewed] = useState(true),
    [summary, setSummary] = useState<string[]>([]),
    [warnings, setWarnings] = useState<string[]>([]);
  const [inputTab, setInputTab] = useState<"constraints" | "activities">(
      "constraints",
    ),
    [view, setView] = useState<"calendar" | "resources">("calendar");
  const [page, setPage] = useState<"workspace" | "history">("workspace"),
    [history, setHistory] = useState<HistoryRun[]>([]);
  const [constraintEditor, setConstraintEditor] = useState<
      Constraint | "new" | null
    >(null),
    [addingActivity, setAddingActivity] = useState(false),
    [editingActivity, setEditingActivity] = useState<Activity | null>(null),
    [selected, setSelected] = useState<Assignment | null>(null),
    [explanation, setExplanation] = useState<Explanation | null>(null),
    [explainBusy, setExplainBusy] = useState(false),
    [help, setHelp] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null),
    textFileRef = useRef<HTMLInputElement>(null),
    previous = useRef<Assignment[]>([]),
    loadCounter = useRef(0);

  async function load(s: Scenario) {
    const version = ++loadCounter.current;
    setBusy("正在求解示例");
    setError("");
    setNotice("");
    setResult(null);
    setSummary([]);
    setWarnings([]);
    setCustomWeights(null);
    previous.current = [];
    setReviewed(true);
    setScenario(s);
    setInput(SCENARIOS[s].input);
    setPage("workspace");
    setView("calendar");
    try {
      const p = await api<Problem>(`/templates/${s}`);
      if (version !== loadCounter.current) return;
      setProblem(p);
      const r = await api<Result>("/solve", {
        problem: p,
        reviewed: true,
        mode: "balanced",
      });
      if (version !== loadCounter.current) return;
      setMode("balanced");
      setResult(r);
      previous.current = r.assignments;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      if (version === loadCounter.current) setBusy("");
    }
  }
  useEffect(() => {
    api<{ provider: string; version: string }>("/health")
      .then((x) => { setProvider(x.provider); setVersion(x.version); })
      .catch(() => setError("暂时无法连接后端，请确认服务已启动。"));
    // Weight dimensions come from the solver so the UI never hard-codes them.
    api<WeightsMeta>("/weights")
      .then((x) => setWeightsMeta(x))
      .catch(() => setWeightsMeta(null));
    void load("life");
  }, []);
  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(t);
  }, [notice]);
  useEffect(() => {
    if (
      !selected ||
      !problem ||
      !result ||
      !["FEASIBLE", "OPTIMAL"].includes(result.status)
    ) {
      setExplanation(null);
      setExplainBusy(false);
      return;
    }
    let cancelled = false;
    setExplainBusy(true);
    setExplanation(null);
    api<Explanation>("/explain", {
      problem,
      assignments: result.assignments,
      activity_id: selected.activity_id,
      previous: [],
    })
      .then((data) => {
        if (!cancelled) setExplanation(data);
      })
      .catch(() => {
        if (!cancelled) setExplanation(null);
      })
      .finally(() => {
        if (!cancelled) setExplainBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, problem, result]);
  function draft(p: Problem | ((current: Problem | null) => Problem | null)) {
    setProblem(p);
    setResult(null);
    setReviewed(false);
    setError("");
    setSelected(null);
  }
  async function optimize(
    selectedMode: Mode = mode,
    fresh = false,
    // Explicit weight profile for this call. React state updates are async, so a
    // caller that has just changed the profile (e.g. a preset switch clearing the
    // custom weights) must pass it here instead of relying on the closure.
    weightsOverride?: Record<string, number> | null,
  ) {
    if (!problem || !reviewed) return;
    const effectiveWeights =
      weightsOverride === undefined ? customWeights : weightsOverride;
    setBusy("正在组合优化");
    setError("");
    setSelected(null);
    try {
      const r = await api<Result>("/solve", {
        problem,
        reviewed,
        mode: selectedMode,
        previous: fresh ? [] : previous.current,
        ...(effectiveWeights ? { weights: effectiveWeights } : {}),
      });
      setResult(r);
      if (r.assignments.length) previous.current = r.assignments;
      if (r.status === "INFEASIBLE")
        setNotice("检测到约束冲突，已生成诊断结果。");
      else if (r.status === "UNKNOWN")
        setNotice("求解达到时限，已给出可诊断的方向与放宽候选。");
      else if (!["FEASIBLE", "OPTIMAL"].includes(r.status))
        setError("限时内未获得合法解，请减少任务或放宽时间域后重试。");
      else setNotice(`已生成合法计划 · ${r.assignments.length} 项活动`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function parse() {
    if (!problem) return;
    if (input.length > MAX_INPUT_CHARS) {
      setError("每次最多识别 4,000 字，请分段输入或精简文本。");
      return;
    }
    setBusy("正在识别约束");
    setError("");
    try {
      const data = await api<{
        problem: Problem;
        summary: string[];
        warnings: string[];
        provider: string;
      }>("/constraints/parse", { problem, text: input });
      draft(data.problem);
      setSummary(data.summary);
      setWarnings(data.warnings);
      setProvider(data.provider);
      setInputTab("constraints");
      setNotice("请检查识别结果，确认后再生成计划。");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function importFile(file: File) {
    if (!problem) return;
    setBusy("正在读取文件");
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("problem_json", JSON.stringify(problem));
      const response = await fetch("/api/import", {
        method: "POST",
        body: form,
      });
      const data = await readResponse<{ problem: Problem; summary: string[] }>(response);
      draft(data.problem);
      setSummary(data.summary);
      setWarnings([]);
      setNotice("导入完成，请检查并确认新活动。");
      setInputTab("activities");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
      if (fileRef.current) fileRef.current.value = "";
    }
  }
  async function importText(file: File) {
    if (!problem) return;
    setBusy("正在读取文本");
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const response = await fetch("/api/import/text", {
        method: "POST",
        body: form,
      });
      const data = await readResponse<{ kind: string; text: string; chars: number }>(
        response,
      );
      // 提取出的文本进入已有解析管线，不直接改写问题（规格 §11：确定性提取优先）。
      setInput(data.text);
      setInputTab("constraints");
      setNotice(
        `已从 ${data.kind.toUpperCase()} 提取 ${data.chars} 个字符，请点击“识别约束”再确认。`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
      if (textFileRef.current) textFileRef.current.value = "";
    }
  }
  async function conflict() {
    if (!problem) return;
    setBusy("正在建立冲突样例");
    setError("");
    try {
      const p = await api<Problem>("/demo/conflict", problem);
      draft(p);
      setSummary([
        "已加入两个占用同一资源、同一时间的活动限制。请确认后求解，查看真实冲突诊断。",
      ]);
      setWarnings([]);
      setInputTab("constraints");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function repair(constraint_id: string) {
    if (!problem) return;
    setBusy("正在验证并应用修复");
    setError("");
    try {
      const data = await api<{ problem: Problem; result: Result }>("/repair", {
        problem,
        reviewed: true,
        mode,
        ...(customWeights ? { weights: customWeights } : {}),
        previous: previous.current,
        constraint_id,
      });
      setProblem(data.problem);
      setResult(data.result);
      setReviewed(true);
      if (data.result.assignments.length)
        previous.current = data.result.assignments;
      setNotice("已应用你选择的约束放宽方案并重新求解。");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function openHistory() {
    setBusy("正在读取历史");
    setError("");
    try {
      setHistory(await api<HistoryRun[]>("/history"));
      setPage("history");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  function deleteConstraint(c: Constraint) {
    if (!problem) return;
    draft({
      ...problem,
      constraints: problem.constraints.filter((x) => x.id !== c.id),
    });
  }
  function deleteActivity(a: Activity) {
    // Group deletions are batched by React: apply each removal to the latest draft.
    draft((current) => current ? {
      ...current,
      activities: current.activities.filter((x) => x.id !== a.id),
      constraints: current.constraints.filter(
        (c) => c.target !== a.id && c.other !== a.id,
      ),
    } : current);
  }
  function exportPlan(format: "json" | "xlsx" | "pdf" = "json") {
    if (!problem || !result) return;
    if (format === "json") {
      const contents = JSON.stringify({ problem, result }, null, 2);
      const url = URL.createObjectURL(
        new Blob([contents], { type: "application/json" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "atlas-plan.json";
      a.click();
      URL.revokeObjectURL(url);
      return;
    }
    // XLSX/PDF are rendered by the backend from the exact result on screen.
    setError("");
    setBusy(format === "xlsx" ? "正在导出 Excel…" : "正在导出 PDF…");
    void exportPlanRequest(format, { problem, result })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "导出失败，请重试。"),
      )
      .finally(() => setBusy(""));
  }
  const metric = result?.metrics;
  const active =
    selected && problem?.activities.find((a) => a.id === selected.activity_id);
  const totalHours =
    problem?.activities
      .filter((a) => a.category !== "sleep" && !a.optional)
      .reduce((s, a) => s + a.duration / 2, 0) ?? 0;
  const fixedCount =
    problem?.constraints.filter((c) => c.type === "fixed_time").length ?? 0;
  const title = SCENARIOS[scenario];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("workspace");
          }}
        >
          <span className="brand-mark">Σ</span>
          <span>
            ATLAS<span className="brand-sigma">–Σ</span>
            <small>智能调度与组合优化</small>
          </span>
        </a>
        <div className="workspace-label">
          <span className="workspace-avatar">A</span>
          <div>
            我的工作空间<small>比赛演示版</small>
          </div>
          <ChevronDown size={14} />
        </div>
        <div className="nav-label">工作空间</div>
        <button
          disabled={!!busy}
          className={`nav-item ${page === "workspace" ? "active" : ""}`}
          onClick={() => setPage("workspace")}
        >
          <LayoutDashboard size={18} />
          调度工作台
          <ChevronRight size={15} />
        </button>
        <button
          disabled={!!busy}
          className={`nav-item ${page === "history" ? "active" : ""}`}
          onClick={openHistory}
        >
          <History size={18} />
          求解历史
        </button>
        <div className="nav-label scenarios-label">应用场景</div>
        {(Object.keys(SCENARIOS) as Scenario[]).map((s) => {
          const Icon = SCENARIO_ICONS[s];
          return (
            <button
              disabled={!!busy}
              key={s}
              className={`scenario-nav ${scenario === s ? "selected" : ""}`}
              onClick={() => void load(s)}
            >
              <Icon size={17} />
              <span>{SCENARIOS[s].title}</span>
              {scenario === s && <span className="scenario-dot" />}
            </button>
          );
        })}
        <div className="sidebar-note">
          <Workflow size={22} />
          <strong>一个引擎，多种可能。</strong>
          <p>
            需求理解 · 约束建模
            <br />
            组合优化 · 冲突修复
          </p>
          <div className="mini-flow">
            <span />
            <i />
            <span />
            <i />
            <span />
            <i />
            <span />
          </div>
        </div>
        <div className="sidebar-bottom">
          <button className="nav-item" onClick={() => setHelp(true)}>
            <CircleHelp size={18} />
            使用指南
            <ArrowUpRight size={15} />
          </button>
          <div className="profile">
            <span>我</span>
            <div>
              个人工作空间<small>ATLAS-Σ{version ? ` v${version}` : ""}</small>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <Layers3 size={17} />
            <span>工作空间</span>
            <ChevronRight size={14} />
            <strong>{page === "history" ? "求解历史" : title.title}</strong>
          </div>
          <div className="topbar-right">
            <span className="engine-health">
              <span />
              CP-SAT 引擎
            </span>
            <span className="demo-badge">{provider === "demo" ? "DEMO" : provider.toUpperCase()}</span>
            <button
              className="icon-button"
              aria-label="使用指南"
              onClick={() => setHelp(true)}
            >
              <CircleHelp size={18} />
            </button>
          </div>
        </header>
        <main className="main-content">
          <div className="scenario-chips" role="tablist" aria-label="应用场景">
            {(Object.keys(SCENARIOS) as Scenario[]).map((s) => {
              const Icon = SCENARIO_ICONS[s];
              return (
                <button
                  key={s}
                  role="tab"
                  aria-selected={scenario === s}
                  disabled={!!busy}
                  className={`scenario-chip ${scenario === s ? "active" : ""}`}
                  onClick={() => void load(s)}
                >
                  <Icon size={14} />
                  {SCENARIOS[s].title}
                </button>
              );
            })}
          </div>
          <section className="page-heading">
            <div>
              <div className="eyebrow">
                {page === "history"
                  ? "SOLVE HISTORY"
                  : `${title.en} / 调度工作台`}
              </div>
              <h1>
                {page === "history" ? "每一次优化，都有迹可循。" : title.title}
                <span className="heading-dot" />
              </h1>
              <p>
                {page === "history"
                  ? "查看真实求解记录，恢复任务、约束与结果。"
                  : title.description}
              </p>
            </div>
            <div className="heading-actions">
              <button
                className="secondary"
                disabled={!!busy}
                onClick={() => void load(scenario)}
              >
                <RotateCcw size={15} />
                恢复示例
              </button>
              <button
                className="primary"
                disabled={!!busy || !problem}
                onClick={() => setAddingActivity(true)}
              >
                <Plus size={16} />
                添加活动
              </button>
            </div>
          </section>
          {error && (
            <div className="message error" role="alert">
              <AlertTriangle size={17} />
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="关闭错误">
                <X size={15} />
              </button>
            </div>
          )}
          {notice && (
            <div className="toast" role="status">
              <CheckCircle2 size={17} />
              {notice}
              <button onClick={() => setNotice("")} aria-label="关闭提示">
                <X size={14} />
              </button>
            </div>
          )}
          {page === "history" ? (
            <section className="history-panel panel">
              <div className="panel-heading">
                <h2>最近求解</h2>
                <span>{history.length} 条记录</span>
              </div>
              {history.length === 0 ? (
                <div className="empty-state">
                  <History size={30} />
                  <p>生成第一份计划后，求解记录会保存在这里。</p>
                </div>
              ) : (
                history.map((h) => (
                  <button
                    className="history-row"
                    key={h.id}
                    disabled={!!busy}
                    onClick={() => {
                      setProblem(h.problem);
                      setResult(h.result);
                      previous.current = h.result.assignments;
                      setScenario(h.problem.scenario);
                      setInput(SCENARIOS[h.problem.scenario].input);
                      setReviewed(true);
                      setSummary([]);
                      setWarnings([]);
                      setPage("workspace");
                      setMode("balanced");
                      setCustomWeights(h.result.objective?.weights ?? null);
                    }}
                  >
                    <span className="history-icon">
                      <CalendarDays size={20} />
                    </span>
                    <div>
                      <strong>{h.problem.name}</strong>
                      <small>
                        {new Date(h.created_at).toLocaleString("zh-CN")} ·{" "}
                        {h.result.metrics.activities} 项活动
                      </small>
                    </div>
                    <span
                      className={`status-pill ${h.result.status === "INFEASIBLE" ? "bad" : ""}`}
                    >
                      {h.result.status}
                    </span>
                    <span>{h.result.metrics.solve_time}s</span>
                    <ChevronRight size={18} />
                  </button>
                ))
              )}
            </section>
          ) : (
            <>
              <section className="overview">
                <div>
                  <span className="stat-icon blue">
                    <Layers3 size={19} />
                  </span>
                  <div>
                    <span>待编排活动</span>
                    <strong>
                      {problem?.activities.length ?? "—"}
                      <small>项</small>
                    </strong>
                  </div>
                </div>
                <div>
                  <span className="stat-icon purple">
                    <LockKeyhole size={19} />
                  </span>
                  <div>
                    <span>显式约束</span>
                    <strong>
                      {problem?.constraints.length ?? "—"}
                      <small>条</small>
                    </strong>
                  </div>
                </div>
                <div>
                  <span className="stat-icon teal">
                    <Clock3 size={19} />
                  </span>
                  <div>
                    <span>本周任务时长</span>
                    <strong>
                      {totalHours}
                      <small>小时 · 不含睡眠</small>
                    </strong>
                  </div>
                </div>
                <div>
                  <span className="stat-icon orange">
                    <ShieldCheck size={19} />
                  </span>
                  <div>
                    <span>
                      {metric?.hard_violations === 0
                        ? "方案校验通过"
                        : "固定日程"}
                    </span>
                    <strong>
                      {metric?.hard_violations === 0 ? "0" : fixedCount}
                      <small>
                        {metric?.hard_violations === 0
                          ? "硬约束违反"
                          : "项 · 不可移动"}
                      </small>
                    </strong>
                  </div>
                </div>
              </section>
              <div className="workspace-grid">
                <InputPanel
                  problem={problem}
                  busy={busy}
                  provider={provider}
                  input={input}
                  setInput={setInput}
                  parse={parse}
                  scenario={scenario}
                  summary={summary}
                  warnings={warnings}
                  inputTab={inputTab}
                  setInputTab={setInputTab}
                  setConstraintEditor={setConstraintEditor}
                  deleteConstraint={deleteConstraint}
                  deleteActivity={deleteActivity}
                  editActivity={setEditingActivity}
                  mode={mode}
                  setMode={setMode}
                  weightsMeta={weightsMeta}
                  customWeights={customWeights}
                  setCustomWeights={setCustomWeights}
                  setHelp={setHelp}
                  reviewed={reviewed}
                  setReviewed={setReviewed}
                  optimize={optimize}
                  previous={previous}
                  fileRef={fileRef}
                  importFile={importFile}
                  textFileRef={textFileRef}
                  importText={importText}
                />
                <ResultPanel
                  problem={problem}
                  result={result}
                  busy={busy}
                  view={view}
                  setView={setView}
                  summary={summary}
                  exportPlan={exportPlan}
                  repair={repair}
                  setSelected={setSelected}
                />
              </div>
              <footer className="workspace-footer">
                <span>
                  <Workflow size={14} />
                  Understand <ChevronRight size={12} />
                  Model <ChevronRight size={12} />
                  Optimize <ChevronRight size={12} />
                  Explain <ChevronRight size={12} />
                  Repair
                </span>
                <button
                  disabled={
                    !!busy ||
                    !problem?.activities.length ||
                    problem.constraints.some((c) =>
                      c.id.startsWith("demo_conflict"),
                    )
                  }
                  onClick={conflict}
                >
                  <FlaskConical size={14} />
                  试试冲突诊断
                  <ArrowUpRight size={13} />
                </button>
              </footer>
            </>
          )}
        </main>
      </div>
      {problem && constraintEditor && (
        <ConstraintEditor
          problem={problem}
          initial={constraintEditor === "new" ? undefined : constraintEditor}
          onClose={() => setConstraintEditor(null)}
          onSave={async (c) => {
            try {
              const p = {
                ...problem,
                constraints: [
                  ...problem.constraints.filter((x) => x.id !== c.id),
                  c,
                ],
              };
              await api("/constraints/validate", p);
              draft(p);
              setConstraintEditor(null);
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        />
      )}
      {problem && (addingActivity || editingActivity) && (
        <ActivityEditor
          problem={problem}
          initial={editingActivity ?? undefined}
          onClose={() => {
            setAddingActivity(false);
            setEditingActivity(null);
          }}
          onSave={async (a, c) => {
            try {
              const activities = editingActivity
                ? problem.activities.map((x) => (x.id === a.id ? a : x))
                : [...problem.activities, a];
              const constraints = editingActivity
                ? problem.constraints.filter(
                    (x) =>
                      !(
                        x.type === "fixed_time" &&
                        x.target === editingActivity.id
                      ),
                  )
                : problem.constraints;
              const p = {
                ...problem,
                activities,
                constraints: c ? [...constraints, c] : constraints,
              };
              await api("/constraints/validate", p);
              draft(p);
              setAddingActivity(false);
              setEditingActivity(null);
              setInputTab("activities");
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        />
      )}
      {selected && active && problem && (
        <Dialog title={active.name} onClose={() => setSelected(null)}>
          <div className="event-detail">
            <span
              className={`category-badge ${(CATEGORIES[active.category] ?? CATEGORIES.study).color}`}
            >
              {(CATEGORIES[active.category] ?? CATEGORIES.study).label}
            </span>
            <h3>
              {DAYS[Math.floor(selected.start / 48)]} {clock(selected.start)}–
              {selected.end % 48 === 0 ? "24:00" : clock(selected.end)}
            </h3>
            <p>
              连续 {(selected.end - selected.start) / 2} 小时 ·{" "}
              {active.optional ? "可选活动" : "必须完成"}
            </p>
            <h4>
              <Sparkles size={16} />
              为什么排在这个时间？
            </h4>
            {explanation?.narrative && (
              <div className="narrative">
                <p>{explanation.narrative.headline}</p>
                {explanation.narrative.bullets.length > 0 && (
                  <ul>
                    {explanation.narrative.bullets.map((b, i) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ul>
                )}
                <small>由 LLM 依据本次求解事实生成</small>
              </div>
            )}
            {explanation ? (
              <div className="why-list">
                {explanation.reasons.map((reason, index) => (
                  <article
                    className={`why-item why-${reason.kind}`}
                    key={`${reason.kind}-${index}`}
                  >
                    <strong>{reason.title}</strong>
                    <p>{reason.detail}</p>
                  </article>
                ))}
              </div>
            ) : explainBusy ? (
              <p className="why-loading">
                <Loader2 size={15} className="spin" />
                正在根据本次求解数据生成解释…
              </p>
            ) : (
              <ul>
                <li>在该活动允许的日期与时间域内。</li>
                <li>占用资源均未超过可用并发容量。</li>
                {active.resources.map((r) => (
                  <li key={r}>
                    使用资源：{problem.resources.find((x) => x.id === r)?.name}
                  </li>
                ))}
                {selected.room_id && (
                  <li>
                    教室：
                    {
                      problem.resources.find((x) => x.id === selected.room_id)
                        ?.name
                    }
                    ，已检查类型和座位容量。
                  </li>
                )}
                {problem.constraints
                  .filter((c) =>
                    [
                      active.id,
                      active.category,
                      ...active.resources,
                      "*",
                    ].includes(c.target),
                  )
                  .map((c) => (
                    <li key={c.id}>
                      {c.label}
                      {c.level === "soft"
                        ? "（优化偏好）"
                        : "（硬约束已通过）"}
                    </li>
                  ))}
              </ul>
            )}
            <div className="form-note">
              {explanation
                ? `单项活动时间筛选得到 ${explanation.candidate_slots_total} 个候选开始时段，未逐项验证其他活动的资源占用及先后关系。当前方案已经求解并独立校验。`
                : "这是依据求解数据生成的校验说明，不代表该时间是唯一可行选择。"}
            </div>
          </div>
        </Dialog>
      )}
      {help && (
        <Dialog title="使用 ATLAS-Σ" onClose={() => setHelp(false)}>
          <div className="help-content">
            <ol>
              <li>
                <strong>选择一个场景</strong>
                <p>加载真实示例，多个场景共用一个 CP-SAT 求解内核。</p>
              </li>
              <li>
                <strong>描述安排或导入文件</strong>
                <p>
                  识别结果会成为任务与约束。离线模式支持示例句式；完整 LLM
                  解析需要服务端配置 OpenAI 或 DeepSeek。
                </p>
              </li>
              <li>
                <strong>检查并确认约束</strong>
                <p>
                  编辑、删除或新增约束，再勾选确认。固定事项必须给出明确时间。
                </p>
              </li>
              <li>
                <strong>生成计划与重新优化</strong>
                <p>
                  高效模式偏向紧凑，均衡模式兼顾每日负载，稳健模式优先减少已有安排变动。
                </p>
              </li>
              <li>
                <strong>处理冲突</strong>
                <p>
                  点击“试试冲突诊断”，确认后求解。修复候选经过实际求解验证，点击后才会放宽限制。
                </p>
              </li>
            </ol>
            <div className="form-note">
              示例周：2026 年 10 月 12–18 日。30 分钟粒度；个人睡眠示例固定从
              00:00 开始；排课示例按每课时 60
              分钟建模。优化明细显示实际惩罚值，未转换成虚构的百分制评分。
            </div>
          </div>
        </Dialog>
      )}
    </div>
  );
}
