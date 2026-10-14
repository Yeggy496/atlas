import { useState } from "react";
import { Moon, CalendarDays, ArrowUpRight, List, Clock3 } from "lucide-react";
import { calendarLanes } from "./calendarLayout";
import {
  type Problem,
  type Result,
  type Assignment,
  DAYS,
  CATEGORIES,
  clock,
} from "./types";
import "./styles/calendar-polish.css";

type CalendarView = "week" | "day" | "agenda";
const endClock = (slot: number) => slot % 48 === 0 ? "24:00" : clock(slot);

export function Calendar({
  problem,
  result,
  onSelect,
}: {
  problem: Problem;
  result: Result | null;
  onSelect: (x: Assignment) => void;
}) {
  const [calendarView, setCalendarView] = useState<CalendarView>(() =>
    window.matchMedia("(max-width: 760px)").matches ? "agenda" : "week",
  );
  const [selectedDay, setSelectedDay] = useState(0);
  // New plans use an automatic range. Explicit daytime choices belong only
  // to the plan on which the user made the choice.
  const [rangeOverride, setRangeOverride] = useState<{
    runId: string | null;
    full: boolean;
  } | null>(null);
  const activityMap = new Map(problem.activities.map((a) => [a.id, a]));
  const assignments = (result?.assignments ?? []).filter((x) => activityMap.has(x.activity_id));
  const outsideDaytime = assignments.filter((x) =>
    activityMap.get(x.activity_id)?.category !== "sleep" &&
    (x.start % 48 < 16 || (x.end - 1) % 48 >= 44),
  );
  const currentRange = rangeOverride?.runId === (result?.run_id ?? null) ? rangeOverride : null;
  const fullDay = currentRange?.full ?? outsideDaytime.length > 0;
  const startHour = fullDay ? 0 : 8;
  const endHour = fullDay ? 24 : 22;
  const rowHeight = 42;
  const hours = Array.from({ length: endHour - startHour + 1 }, (_, i) => startHour + i);
  const dayEvents = DAYS.map((_, day) => assignments.filter(
    (x) => x.start < day * 48 + endHour * 2 && x.end > day * 48 + startHour * 2,
  ));
  const lanes = dayEvents.map(calendarLanes);
  const sleep = assignments.filter((x) => activityMap.get(x.activity_id)?.category === "sleep");
  const visibleCategories = assignments.length
    ? assignments.map((x) => activityMap.get(x.activity_id)!)
    : problem.activities;
  const legend = Array.from(new Set(visibleCategories
    .filter((a) => fullDay || calendarView === "agenda" || a.category !== "sleep")
    .map((a) => a.category)));
  const sleepDurations = sleep.map((x) => (x.end - x.start) / 2);
  const sameSleepTime = sleep.every((x) => x.start % 48 === sleep[0].start % 48 && x.end % 48 === sleep[0].end % 48);
  const startDate = new Date(`${problem.week_start}T12:00:00`);
  const getDate = (day: number) => {
    const date = new Date(startDate);
    date.setDate(date.getDate() + day);
    return date.getDate();
  };
  const shownDays = calendarView === "day" ? [selectedDay] : DAYS.map((_, i) => i);
  const changeRange = () => setRangeOverride({ runId: result?.run_id ?? null, full: !fullDay });
  return (
    <>
      <div className="calendar-tools">
        <div className="calendar-view-switch" role="group" aria-label="日历显示方式">
          <button type="button" className={calendarView === "week" ? "active" : ""} aria-pressed={calendarView === "week"} onClick={() => setCalendarView("week")}><CalendarDays size={14} />周历</button>
          <button type="button" className={calendarView === "day" ? "active" : ""} aria-pressed={calendarView === "day"} onClick={() => setCalendarView("day")}><Clock3 size={14} />日视图</button>
          <button type="button" className={calendarView === "agenda" ? "active" : ""} aria-pressed={calendarView === "agenda"} onClick={() => setCalendarView("agenda")}><List size={14} />清单</button>
        </div>
        <span className="calendar-view-hint">{calendarView === "agenda" ? "按时间查看完整一周" : calendarView === "day" ? "专注一天，查看完整任务名" : "一眼查看整周安排"}</span>
      </div>
      {calendarView === "day" && <div className="calendar-day-picker" role="group" aria-label="选择日期">{DAYS.map((day, i) => <button type="button" key={day} className={selectedDay === i ? "active" : ""} aria-pressed={selectedDay === i} onClick={() => setSelectedDay(i)}><span>{day}</span><strong>{getDate(i)}</strong></button>)}</div>}
      <div className="calendar-subbar">
        {legend.map((key) => { const category = CATEGORIES[key] ?? CATEGORIES.study; return <span key={key}><span className={`dot ${category.color}`} />{category.label}</span>; })}
        {calendarView !== "agenda" && <button type="button" className={fullDay ? "sleep-toggle selected" : "sleep-toggle"} onClick={changeRange}><Moon size={13} />{fullDay ? "显示白天" : "完整 24 小时"}</button>}
      </div>
      {outsideDaytime.length > 0 && calendarView !== "agenda" && <div className={`calendar-range-note ${fullDay ? "" : "collapsed"}`} role="status"><Clock3 size={14} /><span>{fullDay ? `有 ${outsideDaytime.length} 项早晚活动，已自动展示完整 24 小时。` : `白天视图未完整显示 ${outsideDaytime.length} 项早晚活动。`}</span>{!fullDay && <button type="button" onClick={changeRange}>查看全部</button>}</div>}
      {sleep.length > 0 && calendarView !== "agenda" && <div className="sleep-banner"><Moon size={14} /><span>睡眠已安排</span><strong>{sleep.length} 段 · {Math.min(...sleepDurations) === Math.max(...sleepDurations) ? `每段 ${sleepDurations[0]} 小时` : `${Math.min(...sleepDurations)}–${Math.max(...sleepDurations)} 小时 / 段`}</strong><span className="muted">{sameSleepTime ? `${clock(sleep[0].start)}–${endClock(sleep[0].end)}` : "时间见全天日历"}</span></div>}
      {calendarView === "agenda" ? (
        <div className="calendar-agenda">
          {assignments.length ? DAYS.map((day, dayIndex) => {
            const events = assignments.filter((x) => Math.floor(x.start / 48) === dayIndex).sort((a, b) => a.start - b.start || activityMap.get(a.activity_id)!.name.localeCompare(activityMap.get(b.activity_id)!.name));
            return <section className="agenda-day" key={day}><div className="agenda-day-heading"><strong>{day} · {getDate(dayIndex)} 日</strong><span>{events.length} 项活动</span></div>{events.length ? events.map((x) => {
              const activity = activityMap.get(x.activity_id)!;
              const category = CATEGORIES[activity.category] ?? CATEGORIES.study;
              const resourceNames = [...new Set([...activity.resources, ...Object.keys(activity.demands), ...(x.room_id ? [x.room_id] : [])])].map((id) => problem.resources.find((r) => r.id === id)?.name).filter(Boolean).join(" · ");
              return <button type="button" className="agenda-event" key={x.activity_id} aria-label={`${day} ${clock(x.start)} ${activity.name}`} onClick={() => onSelect(x)}><span className="agenda-time"><strong>{clock(x.start)}</strong><small>{endClock(x.end)}</small></span><span className={`agenda-category ${category.color}`}><span className={`dot ${category.color}`} /></span><span className="agenda-event-body"><strong>{activity.name}</strong><small>{category.label} · {(x.end - x.start) / 2} 小时{resourceNames ? ` · ${resourceNames}` : ""}</small></span><ArrowUpRight size={14} /></button>;
            }) : <p className="agenda-day-empty">这一天暂无已安排活动</p>}</section>;
          }) : <div className="agenda-empty"><CalendarDays size={32} /><h3>还没有生成计划</h3><p>确认左侧约束后，点击“生成计划”。</p></div>}
        </div>
      ) : (
        <div className={`calendar-scroll ${calendarView === "day" ? "calendar-single-day" : ""}`}><div className="calendar-minwidth">
          <div className="week-header"><div className="timezone">GMT+8</div>{shownDays.map((dayIndex) => <div className={`weekday ${dayIndex >= 5 ? "weekend" : ""}`} key={DAYS[dayIndex]}><span>{DAYS[dayIndex]}</span><b>{getDate(dayIndex)}</b></div>)}</div>
          <div className="calendar-body" style={{ height: (endHour - startHour) * rowHeight }}>
            <div className="time-column">{hours.slice(0, -1).map((h) => <span key={h} style={{ top: (h - startHour) * rowHeight }}>{String(h).padStart(2, "0")}:00</span>)}</div>
            <div className="day-columns">{shownDays.map((dayIndex) => <div className={`day-column ${dayIndex >= 5 ? "weekend" : ""}`} key={DAYS[dayIndex]} style={{ backgroundSize: `100% ${rowHeight}px` }}>{dayEvents[dayIndex].map((x) => {
              const activity = activityMap.get(x.activity_id)!;
              const category = CATEGORIES[activity.category] ?? CATEGORIES.study;
              const { lane, lanes: count } = lanes[dayIndex].get(x.activity_id)!;
              const visibleStart = Math.max(x.start - dayIndex * 48, startHour * 2);
              const visibleEnd = Math.min(x.end - dayIndex * 48, endHour * 2);
              return <button type="button" aria-label={`${DAYS[dayIndex]} ${clock(x.start)} ${activity.name}`} title={`${activity.name} ${clock(x.start)}–${endClock(x.end)}`} onClick={() => onSelect(x)} className={`calendar-event ${category.color} ${x.end - x.start <= 1 ? "short" : ""}`} key={x.activity_id} style={{ top: ((visibleStart - startHour * 2) * rowHeight) / 2 + 2, height: Math.max(18, ((visibleEnd - visibleStart) * rowHeight) / 2 - 4), left: `calc(${lane * 100 / count}% + 4px)`, right: `calc(${(count - lane - 1) * 100 / count}% + 4px)` }}><strong>{activity.name}</strong>{x.end - x.start > 1 && <small>{clock(x.start)}–{endClock(x.end)}</small>}{x.end - x.start >= 4 && x.room_id && <small className="event-location">{problem.resources.find((r) => r.id === x.room_id)?.name}</small>}</button>;
            })}</div>)}</div>
            {!assignments.length && <div className="calendar-empty"><CalendarDays size={36} /><h3>为这一周腾出更多可能</h3><p>确认左侧约束后，点击“生成计划”。</p></div>}
            {assignments.length > 0 && calendarView === "day" && dayEvents[selectedDay].length === 0 && <div className="calendar-empty"><CalendarDays size={32} /><h3>这一天暂无活动</h3><p>选择其他日期，或切换清单查看完整一周。</p></div>}
          </div>
        </div></div>
      )}
      <div className="calendar-footer"><span><span className="dot blue" />30 分钟时间粒度</span><span>点击活动查看安排依据 <ArrowUpRight size={13} /></span></div>
    </>
  );
}
