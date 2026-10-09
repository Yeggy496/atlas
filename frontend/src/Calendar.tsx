import { useState } from "react";
import { Moon, CalendarDays, ArrowUpRight } from "lucide-react";
import {
  type Problem,
  type Result,
  type Assignment,
  DAYS,
  CATEGORIES,
  clock,
} from "./types";

export function Calendar({
  problem,
  result,
  onSelect,
}: {
  problem: Problem;
  result: Result | null;
  onSelect: (x: Assignment) => void;
}) {
  const [fullDay, setFullDay] = useState(false);
  const startHour = fullDay ? 0 : 8,
    endHour = fullDay ? 24 : 22,
    rowHeight = 42;
  const hours = Array.from(
    { length: endHour - startHour + 1 },
    (_, i) => startHour + i,
  );
  const assignments = result?.assignments ?? [];
  const sleep = assignments.filter(
    (x) =>
      problem.activities.find((a) => a.id === x.activity_id)?.category ===
      "sleep",
  );
  const startDate = new Date(`${problem.week_start}T12:00:00`);
  const getDate = (day: number) => {
    const date = new Date(startDate);
    date.setDate(date.getDate() + day);
    return date.getDate();
  };
  return (
    <>
      <div className="calendar-subbar">
        <span>
          <span className="dot blue" />
          课程
        </span>
        <span>
          <span className="dot purple" />
          学习
        </span>
        <span>
          <span className="dot teal" />
          {problem.scenario === "life" ? "作业" : "实验"}
        </span>
        <span>
          <span className="dot orange" />
          运动
        </span>
        <button
          className={fullDay ? "sleep-toggle selected" : "sleep-toggle"}
          onClick={() => setFullDay(!fullDay)}
        >
          <Moon size={13} />
          {fullDay ? "显示白天" : "完整 24 小时"}
        </button>
      </div>
      {sleep.length > 0 && (
        <div className="sleep-banner">
          <Moon size={14} />
          <span>睡眠已安排</span>
          <strong>
            {sleep.length} 晚 · 每晚{" "}
            {((sleep[0].end - sleep[0].start) / 2).toFixed(0)} 小时
          </strong>
          <span className="muted">
            {clock(sleep[0].start)}–{clock(sleep[0].end)}
          </span>
        </div>
      )}
      <div className="calendar-scroll">
        <div className="calendar-minwidth">
          <div className="week-header">
            <div className="timezone">GMT+8</div>
            {DAYS.map((d, i) => (
              <div className={`weekday ${i >= 5 ? "weekend" : ""}`} key={d}>
                <span>{d}</span>
                <b>{getDate(i)}</b>
              </div>
            ))}
          </div>
          <div
            className="calendar-body"
            style={{ height: (endHour - startHour) * rowHeight }}
          >
            <div className="time-column">
              {hours.slice(0, -1).map((h) => (
                <span key={h} style={{ top: (h - startHour) * rowHeight }}>
                  {String(h).padStart(2, "0")}:00
                </span>
              ))}
            </div>
            <div className="day-columns">
              {DAYS.map((day, dayIndex) => (
                <div
                  className={`day-column ${dayIndex >= 5 ? "weekend" : ""}`}
                  key={day}
                  style={{ backgroundSize: `100% ${rowHeight}px` }}
                >
                  {assignments
                    .filter(
                      (x) =>
                        x.start >= dayIndex * 48 + startHour * 2 &&
                        x.start < dayIndex * 48 + endHour * 2,
                    )
                    .map((x) => {
                      const a = problem.activities.find(
                        (a) => a.id === x.activity_id,
                      )!;
                      const category =
                        CATEGORIES[a.category] ?? CATEGORIES.study;
                      const concurrent = assignments.filter(
                        (y) =>
                          y.activity_id !== x.activity_id &&
                          y.start < x.end &&
                          y.end > x.start &&
                          Math.floor(y.start / 48) === dayIndex,
                      );
                      const overlaps =
                        concurrent.length > 0 && problem.scenario === "lab";
                      const lane = overlaps
                        ? a.resources.includes("teamB")
                          ? 1
                          : 0
                        : 0;
                      return (
                        <button
                          aria-label={`${day} ${clock(x.start)} ${a.name}`}
                          title={`${a.name} ${clock(x.start)}–${clock(x.end)}`}
                          onClick={() => onSelect(x)}
                          className={`calendar-event ${category.color} ${x.end - x.start <= 1 ? "short" : ""}`}
                          key={x.activity_id}
                          style={{
                            top:
                              (((x.start % 48) - startHour * 2) * rowHeight) /
                                2 +
                              2,
                            height: Math.max(
                              18,
                              ((Math.min(x.end % 48 || 48, endHour * 2) -
                                (x.start % 48)) *
                                rowHeight) /
                                2 -
                                4,
                            ),
                            left: overlaps ? `${lane * 50 + 3}%` : 4,
                            right: overlaps ? `${(1 - lane) * 50 + 3}%` : 4,
                          }}
                        >
                          <strong>{a.name}</strong>
                          {x.end - x.start > 1 && (
                            <small>
                              {clock(x.start)}–
                              {x.end % 48 === 0 ? "24:00" : clock(x.end)}
                            </small>
                          )}
                          {x.end - x.start >= 4 && x.room_id && (
                            <small className="event-location">
                              {
                                problem.resources.find(
                                  (r) => r.id === x.room_id,
                                )?.name
                              }
                            </small>
                          )}
                        </button>
                      );
                    })}
                </div>
              ))}
            </div>
            {!assignments.length && (
              <div className="calendar-empty">
                <CalendarDays size={36} />
                <h3>为这一周腾出更多可能</h3>
                <p>确认左侧约束后，点击“生成计划”。</p>
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="calendar-footer">
        <span>
          <span className="dot blue" />
          30 分钟时间粒度
        </span>
        <span>
          点击活动查看安排依据 <ArrowUpRight size={13} />
        </span>
      </div>
    </>
  );
}
