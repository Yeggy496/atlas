import { useMemo } from "react";
import { RotateCcw, SlidersHorizontal } from "lucide-react";
import type { Mode, WeightsMeta } from "./types";

interface Props {
  meta: WeightsMeta | null;
  mode: Mode;
  // null => preset is in effect; a record => the user's custom profile.
  weights: Record<string, number> | null;
  appliedWeights: Record<string, number> | null;
  reviewed: boolean;
  onChange: (next: Record<string, number> | null) => void;
  // undefined uses the current profile; null explicitly applies the preset.
  onApply: (override?: Record<string, number> | null) => void;
  busy: boolean;
}

const BASE_MAX = 120;

export function WeightPanel({ meta, mode, weights, appliedWeights, reviewed, onChange, onApply, busy }: Props) {
  const preset = meta?.presets?.[mode];
  const active = useMemo(
    () => weights ?? preset ?? {},
    [weights, preset],
  );

  if (!meta) {
    return (
      <div className="weight-panel">
        <div className="weight-panel-head">
          <SlidersHorizontal size={13} />
          <span>自定义权重</span>
        </div>
        <p className="weight-empty">正在读取求解器权重维度…</p>
      </div>
    );
  }

  const setKey = (key: string, value: number) => {
    onChange({ ...active, [key]: value });
  };
  const applied = !!weights && !!appliedWeights &&
    Object.entries(weights).every(([key, value]) => appliedWeights[key] === value);

  return (
    <div className="weight-panel">
      <div className="weight-panel-head">
        <SlidersHorizontal size={13} />
        <span>自定义权重</span>
        <button
          className="weight-reset"
          disabled={busy || !weights}
          title={`恢复「${
            { efficient: "高效", balanced: "均衡", robust: "稳健" }[mode]
          }」预设权重${reviewed ? "并重新求解" : ""}`}
          onClick={() => {
            onChange(null);
            onApply(null);
          }}
        >
          <RotateCcw size={12} />
          预设
        </button>
      </div>
      <div className="weight-rows">
        {meta.dimensions.map((d) => {
          const value = active[d.key] ?? 0;
          const max = Math.max(BASE_MAX, value, ...Object.values(meta.presets).map((profile) => profile[d.key] ?? 0));
          return (
            <label key={d.key} className="weight-row" title={d.hint}>
              <span className="weight-label">{d.label}</span>
              <input
                type="range"
                aria-label={d.label}
                min={0}
                max={max}
                step={1}
                value={value}
                disabled={busy}
                onChange={(e) => setKey(d.key, Number(e.target.value))}
              />
              <span className="weight-value">{value}</span>
            </label>
          );
        })}
      </div>
      <div className="weight-foot">
        <span className="weight-hint">
          {!reviewed ? "确认任务与约束后，再应用权重" : weights ? applied ? "当前计划已应用自定义权重" : "自定义权重待应用" : "当前为预设值，拖动滑块即进入自定义"}
        </span>
        <button
          className="weight-apply"
          disabled={busy || !weights || !reviewed}
          onClick={() => onApply()}
        >
          按自定义重新求解
        </button>
      </div>
    </div>
  );
}
