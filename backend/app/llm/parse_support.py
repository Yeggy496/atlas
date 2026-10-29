"""Bounded structured-output helpers. Never recover a partial schedule as a result."""
import json
import os
import re

from pydantic import ValidationError

from ..schemas import Problem


class IncompleteParse(ValueError):
    pass


class ProviderStopped(ValueError):
    """Provider interruptions and filters are not JSON errors to regenerate around."""


def parse_token_limit(provider):
    default = 24576 if provider == 'deepseek' else 16384
    try:
        return max(1024, min(32768, int(os.getenv(f'{provider.upper()}_MAX_TOKENS', default))))
    except ValueError:
        return default


def completion_content(envelope):
    choice = envelope['choices'][0]
    if choice.get('finish_reason') == 'length':
        raise IncompleteParse('模型输出被截断。')
    if choice.get('finish_reason') not in (None, 'stop'):
        raise ProviderStopped('模型服务未完成本次输出。')
    content = choice['message']['content']
    if not isinstance(content, str) or not content.strip():
        raise ValueError('模型未返回 JSON 文本。')
    # Some compatible gateways wrap JSON in a single code fence. No eval or JSON repair.
    fenced = re.fullmatch(r'\s*```(?:json)?\s*([\s\S]*?)\s*```\s*', content, re.I)
    return fenced.group(1) if fenced else content


def parse_problem_payload(problem: Problem):
    # Keep scope and empty collections explicit. exclude_defaults at the root
    # otherwise drops the selected week and makes "no constraints" ambiguous.
    return {
        'scenario': problem.scenario, 'name': problem.name, 'week_start': problem.week_start,
        'resources': [r.model_dump(exclude_defaults=True) for r in problem.resources],
        'activities': [a.model_dump(exclude_defaults=True) for a in problem.activities],
        'constraints': [c.model_dump(exclude_defaults=True) for c in problem.constraints],
    }


def parse_prompt(problem: Problem):
    example = {'problem': {'scenario': problem.scenario, 'name': problem.name,
        'week_start': problem.week_start, 'resources': [r.model_dump(exclude_defaults=True) for r in problem.resources],
        'activities': [], 'constraints': []}, 'summary': ['识别到的变更'], 'warnings': []}
    return (
        '你是任务与约束解析器，不是排程器。只输出完整 JSON 对象，含 problem、summary、warnings。'
        'problem 是完整修改后的问题，summary/warnings 均为字符串数组。不要输出正式安排、代码或表达式。'
        '严格保持 current_problem.scenario 和 week_start；不擅自切换场景或更改所在周。'
        '保留未被用户要求修改的内容；用户明确要求重新整理或替换示例时，可按其要求删除旧活动和关联约束。'
        '重复描述已有任务时，应复用或更新相应任务及约束，不得重复追加。'
        '每天/每周N次或总共N小时表示修改后该项目的完整数量，不是给旧数量再增加N次或N小时；其余无关任务仍保留。'
        '仅为用户明确提到的课程、会议、学习等创建新任务，不得根据常见课表、专业或示例补充未提及的课程或活动。'
        '用户只说“有课”但没有提供课程名称时，不得猜测具体名称；时间、次数或其他关键信息不明确时在 warnings 中说明需要确认。'
        '用户明确提到的老师、团队、参会人、设备和场地，若不在当前资源中，必须新增到resources，并用新资源id关联对应活动；不得凭空编造用户未提到的资源。'
        '同名资源优先复用；资源id必须唯一；设备数量用capacity，教室及会议室人数用seats、room_type。'
        '会议/实验/课程明确需要场地时，每项活动都要在room_options列出符合要求的场地id，required_seats使用明确给出的人数；设备、团队和参会人通过resources关联。用户没有说明具体参会人员时，不得把其他会议的参会人臆测为该会议成员。'
        '用户明确说明只有某几台设备或某几间场地时，活动只能使用这些设备或场地；预置资源即使保留，也不得擅自作为额外候选。'
        '每个时间槽为30分钟：半小时=1，1小时=2，8小时=16。每天/多次任务须展开为独立实例，id必须唯一。'
        '每天的days为0至6（周一=0），活动window_start/window_end为当天时刻，范围0至48。'
        '例如00:00-08:00为0-16，11:30-13:30为23-27，21:30为43。'
        '单个活动不能跨午夜，duration必须不大于window_end-window_start。固定时间活动也必须使window_start<=start且start+duration<=window_end；绝不能省略导致固定时间落在默认8:00–22:00之外。'
        '每天23:00至次日07:00睡觉的示例：对本周每天各创建两条活动，一条当天00:00–07:00（duration=14,window_start=0,window_end=14），另一条当天23:00–24:00（duration=2,window_start=46,window_end=48），均占用个人时间资源。每段days只包含当天索引；只表示本周范围内的部分，不生成下周任务。'
        'fixed_time必须指定day及当天start（0至47）；结束由duration决定，不可把整周绝对时刻填入当天时间窗。'
        'deadline.end使用整周绝对时间槽：周三开始前=96，周五18:00前=228。'
        '仅preferred_window为soft，其余约束必须hard；不支持的软偏好应说明，不得偷偷变成硬限制。'
        '“尽量、最好、希望”是偏好，不可通过活动的days/window_start/window_end或daily_limit/deadline偷偷变成硬限制。只有明确“必须、只能、最晚”等条件才建立硬限制；无法表达的软截止时间放入warnings。'
        '任务全部引用当前或本次明确新增的资源id；个人计划的睡眠、用餐、课程和学习都占用已有的个人时间资源。'
        '每条约束target必须是实际任务id、资源id、已使用的category或*，不能用中文活动名代替id。'
        '要在不同天安排同一项目，可使用该项目专属category并添加type=daily_limit,value=1；'
        '例如Python任务都用category=python_study，对python_study设置每日上限1，不能用通用study类别限制所有学习项目。'
        '分成N次不等于分在N天；仅当用户明确要求不同天时才增加每日一次限制，不擅自添加硬约束。'
        '有先后顺序的工作须拆为独立任务并添加前置约束；用户要求连续2小时，应是一项duration=4的任务。工单的group/op_index必须从0连续编号，或者只用precedence关系，不要两种混用。'
        'precedence语义严格是target活动结束后other活动才能开始。例如先做样品制备prep，再做显微观察observe，应为{"type":"precedence","target":"prep","other":"observe"}，绝不能倒置。'
        '多个time_window是同时满足的交集，不是可任选的并集。若要求9:00–12:00或13:00–18:00工作，设置一个9:00–18:00的time_window，再设置12:00–13:00的unavailable；不得创建两个互不相交的time_window。'
        '每条time_window/unavailable/preferred_window的start/end都必须在0至48内且start小于end；固定时间约束只能指向具体活动。'
        'precedence/min_gap/consecutive的target与other都必须是实际任务id；不要用group来表达普通重复任务，group专用于有序工序。'
        '省略未改变的默认字段，避免给每个任务反复输出全部默认属性，但不得省略用户要求或输出省略号。'
        '最多100活动、50资源、200约束。只使用Schema支持的字段与类型，不要输出自然语言类型名称。'
        'JSON结构示例（空数组仅演示结构，实际必须填入识别到的完整任务）：'
        + json.dumps(example, ensure_ascii=False, separators=(',', ':'))
        + '\nSchema:\n' + json.dumps(Problem.model_json_schema(), ensure_ascii=False, separators=(',', ':')))


def repair_feedback(error):
    if isinstance(error, IncompleteParse):
        detail = '上次返回因为输出长度不足而截断，不能作为完整结果。'
    elif isinstance(error, ValidationError):
        detail = json.dumps(error.errors(include_input=False, include_context=False, include_url=False)[:12], ensure_ascii=False)
    elif isinstance(error, json.JSONDecodeError):
        detail = f'不是有效JSON，错误位置为第{error.lineno}行第{error.colno}列。'
    else:
        detail = str(error)[:350] or 'JSON结构不完整，或场景/所在周与输入问题不一致。'
    return ('上次输出没有通过校验：' + detail + '\n请重新输出完整且可校验的JSON，不要续写片段。'
            '修正字段、重复id、资源或任务引用；保留用户提出的所有要求，不得通过丢弃任务逃避校验。'
            'scenario和week_start必须与最初current_problem完全一致。省略默认值以减少篇幅。')


def suggested_scenario(problem: Problem, text: str):
    """A narrow, reversible suggestion, not an automatic domain switch."""
    if problem.scenario == 'life':
        return None
    explicit = bool(re.search(r'个人(?:周|一周|生活)?计划|个人日程', text))
    cues = sum(bool(re.search(pattern, text)) for pattern in [
        r'睡眠|睡.{0,6}小时', r'午饭|晚饭|午餐|晚餐', r'跑步|健身', r'作业|英语复习|Python学习'])
    return 'life' if explicit and cues >= 1 or cues >= 3 else None
