"""Reproducible comparison harness for the OptiDay competition evidence.

Implements the project's own test system (spec sections 36-37 and TABLE 4): the
same instances are handled by a random baseline, a simple greedy baseline, an
optional Direct-LLM baseline, and the OptiDay CP-SAT core. Every published
number comes from a real run of this repository's code; nothing is hard-coded.

    python scripts/benchmark.py
    python scripts/benchmark.py --scenario life academic lab
    python scripts/benchmark.py --out-dir .

Outputs (default: repository root):
    benchmark_results.json   machine-readable raw metrics
    benchmark_results.md     report / PPT ready tables
and the same tables on stdout.

The Direct-LLM row is filled by a real model only when LLM_PROVIDER is openai or
deepseek and the matching key is set. Otherwise a deterministic offline stand-in
is used and clearly labelled; replace it with a real run before quoting numbers.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'backend'))

from app.adapters import ADAPTERS  # noqa: E402
from app.llm.providers import get_provider  # noqa: E402
from app.schemas import Activity, Assignment, Problem, Resource  # noqa: E402
from app.solver.constraints import candidates  # noqa: E402
from app.solver.engine import preference_summary, solve  # noqa: E402
from app.solver.validator import verify  # noqa: E402

SCENARIOS = ('life', 'academic', 'lab')
METHODS = ('random', 'greedy', 'llm', 'optiday')
REAL_PROVIDERS = ('openai', 'deepseek')


# --------------------------------------------------------------------------- #
# baselines
# --------------------------------------------------------------------------- #
def _room_fits(problem: Problem, activity: Activity, rooms: dict, room_id):
    if not room_id:
        return True
    room = rooms.get(room_id)
    if room is None:
        return False
    if room.seats < activity.required_seats:
        return False
    if activity.room_type and room.room_type != activity.room_type:
        return False
    return True


def _raw_domain(problem: Problem, activity: Activity, rooms: dict):
    """Every (start, room) in the activity's own day/window and room fit.

    Cross-activity rules (overlap, precedence, daily limits, deadlines) are all
    ignored on purpose: this is the domain a naive scheduler draws from.
    """
    options = [r for r in (activity.room_options or [None]) if _room_fits(problem, activity, rooms, r)]
    for day in sorted(set(activity.days)):
        for local in range(activity.window_start, activity.window_end - activity.duration + 1):
            for room in options:
                yield day * 48 + local, room


def random_schedule(problem: Problem, seed: int = 0):
    """Uniform random slot per activity, ignoring every cross-activity rule."""
    rng = random.Random(seed)
    rooms = {r.id: r for r in problem.resources}
    out = []
    for a in sorted(problem.activities, key=lambda x: x.id):
        options = list(_raw_domain(problem, a, rooms))
        if not options:
            continue
        start, room = rng.choice(options)
        out.append(Assignment(activity_id=a.id, start=start, end=start + a.duration, room_id=room))
    return out


def greedy_schedule(problem: Problem):
    """Earliest-fit greedy.

    Respects the activity's own time domain (window / day / fixed time / deadline)
    and resource capacity, but no ordering, daily-limit or preference rule. It is
    the strong simple baseline a practitioner reaches for first.
    """
    rooms = {r.id: r for r in problem.resources}
    usage = defaultdict(int)
    out = []
    for a in sorted(problem.activities, key=lambda x: (-x.duration, x.priority, x.id)):
        for start, room in candidates(problem, a):
            used = set(a.resources) | set(a.demands)
            if room:
                used.add(room)
            fits = True
            for rid in used:
                need = a.demands.get(rid, 1)
                capacity = rooms[rid].capacity
                for slot in range(start, start + a.duration):
                    if usage[rid, slot] + need > capacity:
                        fits = False
                        break
                if not fits:
                    break
            if fits:
                for rid in used:
                    need = a.demands.get(rid, 1)
                    for slot in range(start, start + a.duration):
                        usage[rid, slot] += need
                out.append(Assignment(activity_id=a.id, start=start, end=start + a.duration, room_id=room))
                break
    return out


def llm_proxy_schedule(problem: Problem):
    """Deterministic offline stand-in for the Direct-LLM baseline.

    A language model asked to "just produce a schedule" returns a plausible table
    but cannot guarantee global feasibility. This reproduces that failure mode
    deterministically so the pipeline and table exist without a key: activities
    are spread across their days and seated at their window start with no
    conflict or ordering check. It is NOT a model; the Direct-LLM row in the
    report must come from a real provider run.
    """
    rooms = {r.id: r for r in problem.resources}
    prefs = defaultdict(list)
    for c in problem.constraints:
        if c.level == 'soft' and c.type == 'preferred_window':
            prefs[c.target].append(c)
    out = []
    for i, a in enumerate(sorted(problem.activities, key=lambda x: x.id)):
        days = sorted(set(a.days))
        if not days:
            continue
        day = days[i % len(days)]
        local = a.window_start
        for c in prefs.get(a.category, []) + prefs.get(a.id, []) + prefs.get('*', []):
            if c.day is None or c.day == day:
                local = max(a.window_start, min(c.start, a.window_end - a.duration))
                break
        local = max(a.window_start, min(local, a.window_end - a.duration))
        options = [r for r in (a.room_options or [None]) if _room_fits(problem, a, rooms, r)]
        out.append(Assignment(activity_id=a.id, start=day * 48 + local,
                              end=day * 48 + local + a.duration, room_id=options[0] if options else None))
    return out


def _as_assignments(items):
    return [x if isinstance(x, Assignment) else Assignment.model_validate(x) for x in items]


def llm_schedule(problem: Problem, provider_name: str):
    """Return (assignments, label). Real provider when configured, else proxy."""
    if provider_name in REAL_PROVIDERS:
        provider = get_provider()
        return _as_assignments(provider.schedule_directly(problem)), provider_name
    return llm_proxy_schedule(problem), 'llm-proxy(offline)'


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def daily_hours(problem: Problem, assignments) -> list:
    activities = {a.id: a for a in problem.activities}
    hours = [0.0] * 7
    for x in assignments:
        a = activities.get(x.activity_id)
        if a is None or a.category == 'sleep':
            continue
        day = x.start // 48
        if 0 <= day < 7:
            hours[day] += (x.end - x.start) / 2
    return hours


def fragmentation(problem: Problem, assignments) -> int:
    """Idle 30-min slots inside each resource's occupied daily span (compactness)."""
    activities = {a.id: a for a in problem.activities}
    spans = defaultdict(list)
    for x in assignments:
        a = activities.get(x.activity_id)
        if a is None or a.category == 'sleep':
            continue
        used = set(a.resources) | set(a.demands)
        if x.room_id:
            used.add(x.room_id)
        for rid in used:
            spans[rid, x.start // 48].append((x.start % 48, x.start % 48 + (x.end - x.start)))
    total = 0
    for entries in spans.values():
        low = min(s for s, _ in entries)
        high = max(e for _, e in entries)
        total += max(0, high - low - sum(e - s for s, e in entries))
    return total


def compute_metrics(problem: Problem, assignments, seconds: float) -> dict:
    activities = {a.id: a for a in problem.activities}
    violations = verify(problem, assignments)
    total, satisfied = preference_summary(problem, assignments, activities)
    hours = daily_hours(problem, assignments)
    required = sum(1 for a in problem.activities if not a.optional)
    return {
        'hard_violations': len(violations),
        'valid': not violations,
        'violations_sample': violations[:8],
        'preference_total': total,
        'preference_satisfied': satisfied,
        'preference_score': round(satisfied / total, 4) if total else 1.0,
        'fragmentation_slots': fragmentation(problem, assignments),
        'daily_load_span_hours': round(max(hours) - min(hours), 2),
        'scheduled': len(assignments),
        'required': required,
        'solve_time': round(seconds, 3),
    }


# --------------------------------------------------------------------------- #
# instances
# --------------------------------------------------------------------------- #
def shipped_instances():
    return [(name, ADAPTERS[name]()) for name in SCENARIOS]


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #
def run_method(method: str, problem: Problem, seed: int, provider_name: str, optiday_seconds):
    started = time.perf_counter()
    if method == 'random':
        assignments, note = random_schedule(problem, seed), '随机合法域，不检查冲突'
    elif method == 'greedy':
        assignments, note = greedy_schedule(problem), '最早可排贪心，仅避让资源占用'
    elif method == 'llm':
        assignments, label = llm_schedule(problem, provider_name)
        note = f'一次性直接排程（{label}）'
    elif method == 'optiday':
        result = solve(problem, 'balanced', seconds=optiday_seconds)
        assignments = _as_assignments(result['assignments'])
        note = f"CP-SAT {result['status']}"
        optiday_metrics = dict(result['metrics'])
        optiday_metrics['status'] = result['status']
    else:
        raise ValueError(f'未知方法 {method}')
    seconds = time.perf_counter() - started
    metrics = compute_metrics(problem, assignments, seconds)
    metrics['method'] = method
    metrics['note'] = note
    if method == 'optiday':
        metrics['solver'] = locals().get('optiday_metrics', {})
    return metrics


def run_benchmark(instances, methods, seed: int, provider_name: str, optiday_seconds):
    rows = []
    for name, problem in instances:
        for method in methods:
            row = run_method(method, problem, seed, provider_name, optiday_seconds)
            row['instance'] = name
            row['scenario'] = problem.scenario
            row['activities'] = len(problem.activities)
            row['resources'] = len(problem.resources)
            row['constraints'] = len(problem.constraints)
            rows.append(row)
            print(f'  {name:<14} {method:<7} violations={row["hard_violations"]:<3} '
                  f'valid={str(row["valid"]):<5} pref={row["preference_score"]:.2f} '
                  f'time={row["solve_time"]:.3f}s')
    return rows


def aggregate(rows, scenario_names):
    """One summary row per method over the shipped scenario instances."""
    names = set(scenario_names)
    summary = {}
    for method in METHODS:
        picked = [r for r in rows if r['method'] == method and r['instance'] in names]
        if not picked:
            continue
        summary[method] = {
            'instances': len(picked),
            'hard_violations': sum(r['hard_violations'] for r in picked),
            'valid_instances': sum(1 for r in picked if r['valid']),
            'preference_score': round(sum(r['preference_score'] for r in picked) / len(picked), 4),
            'fragmentation_slots': sum(r['fragmentation_slots'] for r in picked),
            'daily_load_span_hours': round(sum(r['daily_load_span_hours'] for r in picked) / len(picked), 2),
            'solve_time': round(sum(r['solve_time'] for r in picked) / len(picked), 3),
        }
    return summary


def _md_table(headers, body):
    lines = ['| ' + ' | '.join(headers) + ' |',
             '| ' + ' | '.join('---' for _ in headers) + ' |']
    lines += ['| ' + ' | '.join(str(c) for c in row) + ' |' for row in body]
    return '\n'.join(lines)


def render_markdown(rows, summary, meta):
    per_instance = _md_table(
        ['实例', '方法', '硬约束违反', '合法', '偏好得分', '碎片(slot)', '日负载差(h)', '耗时(s)'],
        [[r['instance'], r['method'], r['hard_violations'], '是' if r['valid'] else '否',
          f"{r['preference_score']:.2f}", r['fragmentation_slots'], r['daily_load_span_hours'],
          f"{r['solve_time']:.3f}"] for r in rows])
    summary_table = _md_table(
        ['方法', '实例数', '硬约束违反合计', '合法实例', '偏好得分', '碎片合计(slot)', '日负载差(h)', '平均耗时(s)'],
        [[m, s['instances'], s['hard_violations'], f"{s['valid_instances']}/{s['instances']}",
          f"{s['preference_score']:.2f}", s['fragmentation_slots'], s['daily_load_span_hours'],
          f"{s['solve_time']:.3f}"] for m, s in summary.items()])
    efficiency = _md_table(
        ['实例', '任务数', '变量数', '模型约束数', '状态', '耗时(s)', '硬约束违反', '合法'],
        [[r['instance'], r['activities'], r.get('solver', {}).get('variables', ''),
          r.get('solver', {}).get('model_constraints', ''), r.get('solver', {}).get('status', ''),
          f"{r['solve_time']:.3f}", r['hard_violations'], '是' if r['valid'] else '否']
         for r in rows if r['method'] == 'optiday'])
    table4 = _md_table(
        ['Method', 'Hard Violations', 'Preference Score', 'Valid'],
        [[m, s['hard_violations'], f"{s['preference_score']:.2f}",
          f"{s['valid_instances']}/{s['instances']}"] for m, s in summary.items()])
    provider_note = '（离线占位，非真实模型）' if meta['provider'] not in REAL_PROVIDERS else ''
    model_line = (f"LLM provider：{meta['provider']} {provider_note}" if 'llm' in meta['methods']
                  else '本轮仅比较调度方法，未进行大模型效果对比。')
    parts = [
        '# OptiDay 对比实验结果',
        '',
        f"生成时间：{meta['generated_at']}　求解器种子：{meta['seed']}　OptiDay 时限：{meta['optiday_seconds']}s",
        model_line,
        '',
        '## 1. 汇总（预置场景实例）',
        '',
        summary_table,
        '',
        '## 2. 逐实例明细',
        '',
        per_instance,
        '',
        '## 3. 报告 TABLE 4 形式',
        '',
        table4,
        '',
        '## 4. 求解规模与耗时（OptiDay，预置场景实例）',
        '',
        efficiency,
        '',
        '> 所有数字均由 scripts/benchmark.py 真实运行得到；OptiDay 一列通过独立校验器 verify() 复核，硬约束违反必须为 0。',
        '> 数据为预置任务，不是真实用户试点。random 不检查跨活动约束；greedy 是简化的最早可行时段法，未实现前置关系、每日上限与偏好。该对比只说明这些实例需要完整约束检查，不代表超越成熟调度算法，也不证明规模泛化。',
    ]
    return '\n'.join(parts) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description='OptiDay comparison benchmark.')
    parser.add_argument('--scenario', nargs='+', choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument('--methods', nargs='+', choices=METHODS, default=list(METHODS))
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--optiday-seconds', type=float, default=float(os.getenv('OPTIDAY_SOLVE_SECONDS', '4')))
    parser.add_argument('--out-dir', type=Path, default=ROOT)
    args = parser.parse_args()

    provider_name = os.getenv('LLM_PROVIDER', 'demo').lower()
    instances = [(n, ADAPTERS[n]()) for n in args.scenario]

    print(f'provider={provider_name}  methods={",".join(args.methods)}  instances={len(instances)}')
    rows = run_benchmark(instances, args.methods, args.seed, provider_name, args.optiday_seconds)

    summary = aggregate(rows, args.scenario)
    meta = {
        'generated_at': datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds'),
        'provider': provider_name,
        'seed': args.seed,
        'optiday_seconds': args.optiday_seconds,
        'methods': args.methods,
    }
    markdown = render_markdown(rows, summary, meta)
    print('\n' + markdown)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / 'benchmark_results.json').write_text(
        json.dumps({'meta': meta, 'rows': rows, 'summary': summary}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    (args.out_dir / 'benchmark_results.md').write_text(markdown, encoding='utf-8')
    print(f'已写入 {args.out_dir / "benchmark_results.json"} 与 {args.out_dir / "benchmark_results.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
