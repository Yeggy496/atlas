"""Provider boundary: model output is data, validated twice before user review."""
import json
import os
import re
from uuid import uuid4
from typing import Protocol
import httpx
from .model_http import model_client
from pydantic import BaseModel, Field, StrictStr
from ..schemas import Problem, Activity, Constraint


class LLMProvider(Protocol):
    def parse_constraints(self, problem: Problem, text: str) -> dict: ...
    def schedule_directly(self, problem: Problem): ...


class ParsedConstraints(BaseModel):
    problem: Problem
    summary: list[StrictStr]
    warnings: list[StrictStr] = Field(default_factory=list)


def request_options(provider: str) -> dict:
    # Constraint extraction needs JSON, not a lengthy reasoning response.
    return {'thinking': {'type': 'disabled'}} if provider == 'deepseek' else {}


def parse_failure_message(error: Exception) -> str:
    # Never include raw exception text: it can contain credentials, URLs or model input.
    prefix = '模型解析未成功：'
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        hint = ('请检查密钥权限或网关访问限制。' if status in (401, 403) else
                '请求频率或额度受限，请稍后重试。' if status == 429 else
                '模型服务暂时繁忙或不可用，请稍后重试；当前任务仍可手工编辑和求解。' if status >= 500 else
                '请检查接口地址、模型名称及网关支持的请求格式。')
        return f'{prefix}模型接口返回 HTTP {status}。{hint}'
    if isinstance(error, httpx.TimeoutException):
        return prefix + '模型接口请求超时，请稍后重试或调整服务端超时设置。'
    if isinstance(error, httpx.RequestError):
        if 'CERTIFICATE_VERIFY_FAILED' in str(error):
            return prefix + '模型接口 HTTPS 证书校验失败，请检查网关证书配置。'
        return prefix + '服务器无法连接模型接口，请检查地址和网络可达性。'
    return prefix + '模型返回数据未通过 JSON 或任务约束校验，请重试或使用手工约束。'


class APIProvider:
    def __init__(self, provider: str):
        self.provider = provider

    def parse_constraints(self, problem: Problem, text: str):
        prefix = self.provider.upper()
        key = os.getenv(f'{prefix}_API_KEY','')
        if not key:
            raise ValueError(f'尚未配置 {prefix}_API_KEY。可切换规则解析或手工编辑约束。')
        default_base = 'https://api.openai.com/v1' if self.provider=='openai' else 'https://api.deepseek.com'
        base = (os.getenv(f'{prefix}_BASE_URL') or default_base).rstrip('/')
        model = os.getenv(f'{prefix}_MODEL','gpt-4.1-mini' if self.provider=='openai' else 'deepseek-flash')
        timeout = float(os.getenv(f'{prefix}_TIMEOUT', '90' if self.provider == 'deepseek' else '35'))
        prompt = ('你是约束解析器，不安排日程。只返回 JSON 对象，包含 problem（完整修改后的问题）、summary（变更说明字符串数组）、warnings（歧义或不支持项字符串数组）。'
                  '每个 slot=30分钟，周一=0，start/end是当天slot；deadline.end是从周一00:00开始的slot。必须保留未修改的输入。'
                  '不能凭空创造课程、设备或人员，未知实体和歧义写入warnings。只使用给定Schema支持的类型。preferred_window必须soft，其余hard。'
                  '重复活动展开为独立实例；学习可拆分为多项；不得输出调度结果、代码或表达式。Schema:\n'+json.dumps(Problem.model_json_schema(),ensure_ascii=False))
        try:
            with model_client(timeout) as client:
                response=client.post(base+'/chat/completions',headers={'Authorization':f'Bearer {key}'},json={'model':model,'temperature':0,'response_format':{'type':'json_object'},'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps({'current_problem':problem.model_dump(),'request':text},ensure_ascii=False)}],**request_options(self.provider)})
                response.raise_for_status()
                content=response.json()['choices'][0]['message']['content']
                if not isinstance(content,str):
                    raise ValueError('模型未返回 JSON 文本。')
                data=json.loads(content)
            return validate_parse(data,self.provider)
        except (httpx.HTTPError,KeyError,IndexError,TypeError,ValueError) as exc:
            raise ValueError(parse_failure_message(exc)) from exc


    def schedule_directly(self, problem: Problem):
        """Ask the model to schedule everything in one shot (Direct-LLM baseline).

        This is the comparison baseline the report needs, so it deliberately does
        NOT go through CP-SAT. The raw model output is only parsed and trimmed to
        known activity ids; the independent validator then measures the real hard
        constraint violations of whatever the model produced.
        """
        prefix = self.provider.upper()
        key = os.getenv(f'{prefix}_API_KEY', '')
        if not key:
            raise ValueError(f'尚未配置 {prefix}_API_KEY，无法运行 Direct-LLM 基线。')
        default_base = 'https://api.openai.com/v1' if self.provider == 'openai' else 'https://api.deepseek.com'
        base = (os.getenv(f'{prefix}_BASE_URL') or default_base).rstrip('/')
        model = os.getenv(f'{prefix}_MODEL', 'gpt-4.1-mini' if self.provider == 'openai' else 'deepseek-flash')
        timeout = float(os.getenv(f'{prefix}_TIMEOUT', '90' if self.provider == 'deepseek' else '35'))
        payload = {'activities': [a.model_dump() for a in problem.activities],
                   'resources': [r.model_dump() for r in problem.resources],
                   'constraints': [c.model_dump() for c in problem.constraints]}
        prompt = ('你是排程助手。请直接给出完整可行的周日程，只返回 JSON 对象 '
                  '{"assignments":[{"activity_id":..., "start":..., "end":..., "room_id":...}]}。'
                  '每个 slot 为 30 分钟，周一 00:00 为 0；room_id 无教室时用 null。不要解释，不要输出代码。')
        try:
            with model_client(timeout) as client:
                response = client.post(base + '/chat/completions', headers={'Authorization': f'Bearer {key}'},
                                       json={'model': model, 'temperature': 0,
                                             'response_format': {'type': 'json_object'},
                                             'messages': [{'role': 'system', 'content': prompt},
                                                          {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
                                             **request_options(self.provider)})
                response.raise_for_status()
                content = response.json()['choices'][0]['message']['content']
                if not isinstance(content, str):
                    raise ValueError('模型未返回 JSON 文本。')
                data = json.loads(content)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise ValueError('模型直接排程未成功，请重试或稍后再跑对比。') from exc
        return validate_schedule(data, problem)


def validate_schedule(data, problem: Problem):
    """Keep only well-formed assignments whose activity id exists in the problem."""
    from ..schemas import Assignment
    items = data.get('assignments') if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError('模型未返回日程数组。')
    known = {a.id for a in problem.activities}
    out = []
    for item in items:
        if not isinstance(item, dict) or item.get('activity_id') not in known:
            continue
        try:
            out.append(Assignment(activity_id=item['activity_id'], start=int(item['start']),
                                  end=int(item['end']), room_id=item.get('room_id')))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def validate_parse(data, provider):
    parsed=ParsedConstraints.model_validate(data)
    return {**parsed.model_dump(),'provider':provider,'requires_review':True}


def _chinese_clock_hour(hour: int, period: str | None) -> int:
    """Interpret explicit Chinese periods; never guess an unstated AM/PM."""
    if not 0 <= hour <= 23:
        raise ValueError('时间的小时须在 0–23 之间。')
    if period in ('下午', '晚上', '晚'):
        if 1 <= hour <= 11:
            return hour + 12
        if period in ('晚上', '晚') and hour == 12:
            return 0
    if period == '凌晨' and hour == 12:
        return 0
    if period == '中午' and hour in (1, 2):
        return hour + 12
    return hour


class DemoProvider:
    """A deliberately small deterministic grammar. Explicitly disclosed in UI."""
    def parse_constraints(self, problem: Problem, text: str):
        p=problem.model_copy(deep=True)
        summary,warnings=[],[]
        def person_resource():
            if any(r.id == 'me' for r in p.resources): return 'me'
            people = [r.id for r in p.resources if r.type == 'person']
            if len(people) == 1: return people[0]
            raise ValueError('规则解析需要明确的个人时间资源；请保留「我的时间」，或在资源管理中只设置一个个人资源。')
        chunks=[s.strip() for s in re.split(r'[，,。；;\n]+',text) if s.strip()]
        used=set()
        token=uuid4().hex[:8]
        def mark(pattern):
            for i,s in enumerate(chunks):
                if re.search(pattern,s,re.I): used.add(i)
        def replace_group(prefix,name,category,durations):
            deleted={a.id for a in p.activities if a.id.startswith(prefix)}
            p.activities=[a for a in p.activities if a.id not in deleted]
            p.constraints=[c for c in p.constraints if c.target not in deleted and c.other not in deleted]
            for i,d in enumerate(durations):
                p.activities.append(Activity(id=f'{prefix}{i}',name=f'{name} {i+1}',duration=d,category=category,resources=[person_resource()]))
        if p.scenario=='life':
            sleep=re.search(r'睡眠?[^\d，。]*?(\d+(?:\.5)?)\s*小时',text)
            if sleep:
                h=float(sleep[1])
                if not 1<=h<=12: raise ValueError('规则解析支持 1–12 小时的睡眠时长。')
                for a in p.activities:
                    if a.category=='sleep': a.duration=int(h*2); a.window_end=int(h*2)
                summary.append(f'每天连续睡眠 {h:g} 小时（预置方案采用 00:00 入睡）')
                mark(r'睡')
            running=re.search(r'跑步\s*(\d+)\s*次',text)
            if running:
                count=int(running[1]); each=re.search(r'每次\s*(\d+(?:\.5)?)\s*小时',text)
                duration=int(float(each[1])*2) if each else 2
                if not 1<=count<=7 or not 1<=duration<=8: raise ValueError('规则解析支持每周 1–7 次跑步，每次 0.5–4 小时。')
                replace_group('run','跑步','exercise',[duration]*count)
                summary.append(f'每周跑步 {count} 次，每次 {duration/2:g} 小时')
                mark(r'跑步|每次')
            pref=re.search(r'(?:最好|尽量|跑步).*?(?:(凌晨|早上|上午|中午|下午|晚上|晚)\s*)?(\d{1,2})\s*(?:点|:00)\s*(?:以?后)',text)
            if pref and ('跑步' in text or running):
                hour=_chinese_clock_hour(int(pref[2]), pref[1])
                if not 0<=hour<22: raise ValueError('跑步偏好时间须早于 22:00。')
                p.constraints=[c for c in p.constraints if not(c.type=='preferred_window' and c.target=='exercise')]
                p.constraints.append(Constraint(id=f'pref_{token}',label=f'跑步尽量安排在 {hour:02}:00 以后',type='preferred_window',target='exercise',level='soft',start=hour*2,end=44,source='demo_parser'))
                summary.append(f'跑步偏好：{hour:02}:00 以后（软约束）'); mark(r'最好|尽量|点以后|点后')
            python=re.search(r'(\d+(?:\.5)?)\s*小时\s*Python|Python\s*(?:学习)?[^\d，。]*?(\d+(?:\.5)?)\s*小时',text,re.I)
            if python:
                slots=int(float(python[1] or python[2])*2)
                if not 1<=slots<=56: raise ValueError('规则解析支持 0.5–28 小时的 Python 总学习时长。')
                durations=[4]*(slots//4)+([slots%4] if slots%4 else [])
                replace_group('python','Python 学习','study',durations)
                summary.append(f'Python 学习共 {slots/2:g} 小时，每次最多 2 小时'); mark(r'Python|连续学习')
            math=re.search(r'高数作业[^，。]*?周([一二三四五六日天])(?:之?前)',text)
            if math:
                day='一二三四五六日'.index(math[1].replace('天','日'))
                if day==0: raise ValueError('周一之前的截止时间在本周规划域之外。')
                amount=re.search(r'高数作业[^\d，。]*?(\d+(?:\.5)?)\s*小时',text)
                if amount:
                    slots=int(float(amount[1])*2)
                    if not 1<=slots<=40: raise ValueError('规则解析支持 0.5–20 小时的作业时长。')
                    replace_group('math','高数作业','homework',[4]*(slots//4)+([slots%4] if slots%4 else []))
                p.constraints=[c for c in p.constraints if not(c.type=='deadline' and c.target.startswith('math'))]
                for a in p.activities:
                    if a.category=='homework': p.constraints.append(Constraint(id=f'deadline_{a.id}_{token}',label=f'{a.name} · 周{math[1]} 00:00 前完成',type='deadline',target=a.id,end=day*48,source='demo_parser'))
                summary.append(f'高数作业在周{math[1]} 00:00 前完成'); mark(r'高数作业')
            meeting=re.search(r'周([一二三四五六日天])\s*(?:(凌晨|早上|上午|中午|下午|晚上|晚)\s*)?(\d{1,2})(?::(\d{2})|点(?:([\d]+)分?|半)?)?[^，。]*?会议',text)
            if meeting:
                day='一二三四五六日'.index(meeting[1].replace('天','日'))
                hour=_chinese_clock_hour(int(meeting[3]), meeting[2])
                minute=int(meeting[4] or meeting[5] or ('30' if '点半' in meeting[0] else '0'))
                if minute not in (0,30): raise ValueError('会议时间请按半小时填写，例如 19:00 或 19:30；没有自动四舍五入。')
                if not 0<=hour<=22: raise ValueError('会议时间必须在 00:00–22:30 内。')
                aid=f'meeting_{token}'
                p.activities.append(Activity(id=aid,name='临时会议',duration=2,category='meeting',resources=[person_resource()],days=[day],window_start=0,window_end=48))
                p.constraints.append(Constraint(id=f'fixed_{token}',label=f'周{meeting[1]} {hour:02}:{minute:02} 临时会议 · 1 小时',type='fixed_time',target=aid,day=day,start=hour*2+minute//30,source='demo_parser'))
                summary.append(f'新增周{meeting[1]} {hour:02}:{minute:02} 会议，默认 1 小时'); mark(r'会议')
        else:
            for r in p.resources:
                if r.name not in text: continue
                match=re.search(re.escape(r.name)+r'[^，。]*?周([一二三四五六日天])(上午|下午|晚上|全天)?[^，。]*?(?:没空|不可用|不能)',text)
                if match:
                    day='一二三四五六日'.index(match[1].replace('天','日')); window={'上午':(0,24),'下午':(24,36),'晚上':(36,48)}.get(match[2],(0,48))
                    p.constraints.append(Constraint(id=f'unavailable_{r.id}_{token}',label=f'{r.name}周{match[1]}{match[2] or "全天"}不可用',type='unavailable',target=r.id,day=day,start=window[0],end=window[1],source='demo_parser'))
                    summary.append(p.constraints[-1].label); mark(re.escape(r.name))
            if '机器学习' in text and re.search(r'连续\s*(?:2|两|二)\s*节',text):
                for a in p.activities:
                    if '机器学习' in a.name: a.duration=4
                summary.append('机器学习每次连续 2 小时（预置课时为 60 分钟）'); mark(r'机器学习')
            if re.search(r'连排|连堂|相邻|紧接|紧挨|接着',text):
                flat=text.replace(' ','')
                mentioned=[a for a in p.activities if a.name.replace(' ','') in flat]
                if len(mentioned)>=2:
                    a,b=mentioned[0],mentioned[1]
                    p.constraints=[c for c in p.constraints if not(c.type=='consecutive' and c.target==a.id)]
                    p.constraints.append(Constraint(id=f'consec_{token}',label=f'{a.name} 与 {b.name} 连排',type='consecutive',target=a.id,other=b.id,source='demo_parser'))
                    summary.append(f'{a.name} 与 {b.name} 连续排布'); mark(r'连排|连堂|相邻|紧接|紧挨|接着')
            if '数据库实验' in text and '计算机实验室' in text:
                for a in p.activities:
                    if '数据库实验' in a.name: a.room_type='computer'
                summary.append('数据库实验限定计算机实验室'); mark(r'数据库实验')
        warnings += [f'未自动处理：{s}。请在任务与约束中手工补充。' for i,s in enumerate(chunks) if i not in used]
        if not summary:
            warnings.insert(0,'规则解析支持的表达有限；当前输入没有生成变更，请手工补充。')
        return validate_parse({'problem':p.model_dump(),'summary':summary,'warnings':warnings},'demo')


def get_provider():
    name=os.getenv('LLM_PROVIDER','demo').lower()
    if name not in ('demo','openai','deepseek'): raise ValueError('LLM_PROVIDER 必须是 demo、openai 或 deepseek。')
    return DemoProvider() if name=='demo' else APIProvider(name)
