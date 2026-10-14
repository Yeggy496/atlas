import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
export function BusyStatus({ busy }: { busy: string }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    setSeconds(0);
    if (!busy) return;
    const start = Date.now();
    const tick = setInterval(() => setSeconds(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(tick);
  }, [busy]);
  if (!busy) return null;
  const hint = busy.includes("识别") ? "AI 正在整理任务与约束，完成后需要你确认。" :
    busy.includes("优化") || busy.includes("方案") || busy.includes("修复") ? "正在检查时间与资源限制；复杂计划可能需要约 30 秒。" : "请稍候，完成后会自动显示结果。";
  return <div className="busy-status" role="status" aria-live="polite"><Loader2 className="spin" size={17}/><div><strong>{busy}<span>已等待 {seconds} 秒</span></strong><p>{seconds >= 40 ? "耗时较长，首次访问时服务器可能正在唤醒。请保持页面打开。" : hint}</p></div></div>;
}
