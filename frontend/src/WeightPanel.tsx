import { useMemo } from "react";
import { RotateCcw, SlidersHorizontal } from "lucide-react";
import type { Mode, WeightsMeta } from "./types";

interface Props {
  meta: WeightsMeta | null;
  mode: Mode;
  // null => preset is in effect; a record => the user's custom profile.
  weights: Record<string, number> | null;
  onChange: (next: Record<string, number> | null) => void;
  // undefined uses the current profile; null explicitly applies the preset.
  onApply: (override?: Record<string, number> | null) => void;
  busy: boolean;
}

// Slider range. Preset values reach 100 for goal, so the track goes to 120 and the
// scale is logarithmic-friendly: small values stay distinguishable near the bottom.
const MAX = 120;

export function WeightPanel({ meta, mode, weights, onChange, onApply, busy }: Props) {
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
          }」预设并重新求解`}
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
          return (
            <label key={d.key} className="weight-row" title={d.hint}>
              <span className="weight-label">{d.label}</span>
              <input
                type="range"
                min={0}
                max={MAX}
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
          {weights ? "自定义生效中" : "当前为预设值，拖动滑块即进入自定义"}
        </span>
        <button
          className="weight-apply"
          disabled={busy || !weights}
          onClick={() => onApply()}
        >
          按自定义重新求解
        </button>
      </div>
    </div>
  );
}
