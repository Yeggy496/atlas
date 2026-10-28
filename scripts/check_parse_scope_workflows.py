"""Browser regression for choosing whether old work is included in a model request.

The parser responses are controlled test doubles; no model key or paid call is used.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8031')
parser.add_argument('--report')
parser.add_argument('--screenshot')
args = parser.parse_args()
text = '周一上午9点到11点上高等数学，周二下午2点到4点上大学英语。'
report = {'checks': [], 'page_errors': [], 'parser': 'controlled responses', 'paid_model_calls': 0}


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    api = browser.new_context()
    template = api.request.get(args.url + '/api/templates/academic').json()
    template['week_start'] = '2026-10-26'
    existing_count = len(template['activities'])
    assert existing_count > 2

    def profile(problem, viewport=None):
        context = browser.new_context(viewport=viewport or {'width': 1440, 'height': 1000})
        previous = ([{'activity_id': problem['activities'][0]['id'], 'start': 18, 'end': 22, 'room_id': None}]
                    if problem['activities'] else [])
        ws = {'problem': deepcopy(problem), 'result': None, 'previous': previous, 'previousProblem': deepcopy(problem),
              'input': text, 'appliedInput': '', 'mode': 'balanced', 'customWeights': None,
              'reviewed': False, 'summary': [], 'warnings': [], 'inputTab': 'constraints', 'view': 'calendar'}
        store = {'schema_version': 1, 'active_scenario': 'academic', 'workspaces': {'academic': ws}}
        context.add_init_script('localStorage.setItem("optiday.workspace.v1",' + json.dumps(json.dumps(store, ensure_ascii=False)) + ')')
        page = context.new_page()
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.goto(args.url, wait_until='networkidle')
        return context, page

    def model_output(payload, extra=False):
        problem = deepcopy(payload['problem'])
        activity = deepcopy(template['activities'][0])
        items = []
        for i, name in enumerate(['高等数学', '大学英语'] + (['线性代数'] if extra else [])):
            item = deepcopy(activity)
            item.update(id='test_course_' + str(i), name=name, days=[i], duration=4, resources=[], demands={}, room_options=[])
            items.append(item)
        problem['activities'] = problem['activities'] + items
        return {'problem': problem, 'summary': ['模拟识别完成'], 'warnings': [], 'provider': 'deepseek', 'requires_review': True}

    def stored(page):
        return page.evaluate('JSON.parse(localStorage.getItem("optiday.workspace.v1")).workspaces.academic')

    def choose(page, name):
        page.get_by_role('button', name='识别约束', exact=True).click()
        dialog = page.get_by_role('dialog', name='如何处理已有任务？')
        expect(dialog).to_be_visible()
        expect(dialog).to_contain_text(f'{existing_count} 项活动')
        dialog.get_by_role('button', name=name, exact=True).click()

    context, page = profile(template)
    requests = []
    def respond(route):
        payload = route.request.post_data_json
        requests.append(deepcopy(payload))
        route.fulfill(status=200, json=model_output(payload))
    context.route('**/api/constraints/parse', respond)
    page.get_by_role('button', name='识别约束', exact=True).click()
    dialog = page.get_by_role('dialog', name='如何处理已有任务？')
    expect(dialog).to_contain_text('没有提到的任务也会继续参与排程')
    assert not requests
    dialog.get_by_role('button', name='取消', exact=True).click()
    assert len(stored(page)['problem']['activities']) == existing_count
    assert page.get_by_label('自然语言需求').input_value() == text
    report['checks'].append('Choosing nothing keeps existing tasks and text and makes no model call')

    choose(page, '只使用本次描述')
    expect(page.locator('.busy-status')).to_have_count(0)
    expect(page.locator('.parse-summary')).to_contain_text('仅按本次描述')
    assert len(requests) == 1 and requests[0]['problem']['activities'] == [] and requests[0]['problem']['constraints'] == []
    assert requests[0]['problem']['resources'] == template['resources'] and requests[0]['problem']['week_start'] == '2026-10-26'
    expect(page.locator('.activity-row')).to_have_count(2)
    expect(page.locator('.activity-row').filter(has_text='机器学习')).to_have_count(0)
    expect(page.get_by_label('我已检查并确认当前任务与约束')).not_to_be_checked()
    assert not stored(page)['previous']
    report['checks'].append('Replace sends an empty task set, keeps resources/week, and presents just two new courses for review')

    page.get_by_role('button', name='撤销修改', exact=True).click()
    page.locator('.input-tabs').get_by_role('button', name='活动', exact=False).click()
    expect(page.locator('.activity-row')).to_have_count(existing_count)
    page.wait_for_function('(n) => JSON.parse(localStorage.getItem("optiday.workspace.v1")).workspaces.academic.problem.activities.length === n', arg=existing_count)
    assert page.get_by_label('自然语言需求').input_value() == text
    assert stored(page)['previous'][0]['activity_id'] == template['activities'][0]['id']
    report['checks'].append('Undo restores the complete previous plan and input')

    choose(page, '保留现有任务并识别')
    expect(page.locator('.busy-status')).to_have_count(0)
    expect(page.locator('.parse-summary')).to_contain_text('保留并更新现有计划')
    assert len(requests[-1]['problem']['activities']) == existing_count
    assert len(requests[-1]['problem']['constraints']) == len(template['constraints'])
    expect(page.locator('.activity-row').filter(has_text='机器学习')).not_to_have_count(0)
    report['checks'].append('Keep sends old tasks and constraints and shows they were retained')
    context.close()

    context, page = profile(template)
    requests = []
    def fail_once(route):
        payload = route.request.post_data_json
        requests.append(deepcopy(payload))
        if len(requests) == 1:
            route.fulfill(status=503, json={'detail': '测试模型暂时不可用'})
        else:
            route.fulfill(status=200, json=model_output(payload))
    context.route('**/api/constraints/parse', fail_once)
    choose(page, '只使用本次描述')
    expect(page.get_by_role('button', name='重试识别')).to_be_visible()
    assert len(stored(page)['problem']['activities']) == existing_count
    assert stored(page)['previous'][0]['activity_id'] == template['activities'][0]['id']
    assert page.get_by_label('自然语言需求').input_value() == text
    page.get_by_role('button', name='重试识别').click()
    expect(page.locator('.activity-row')).to_have_count(2)
    assert len(requests) == 2 and all(req['problem']['activities'] == [] for req in requests)
    report['checks'].append('Failure preserves old work and retry keeps the chosen replacement scope')
    context.close()

    context, page = profile(template)
    def empty_response(route):
        route.fulfill(status=200, json={'problem': route.request.post_data_json['problem'], 'summary': [],
                                      'warnings': ['没有识别出活动'], 'provider': 'deepseek', 'requires_review': True})
    context.route('**/api/constraints/parse', empty_response)
    choose(page, '只使用本次描述')
    expect(page.get_by_role('button', name='重试识别')).to_be_visible()
    expect(page.locator('body')).to_contain_text('没有识别出活动，原计划未改变')
    assert len(stored(page)['problem']['activities']) == existing_count
    report['checks'].append('A successful but empty model response does not erase the previous plan')
    context.close()

    blank = deepcopy(template)
    blank['activities'] = []
    blank['constraints'] = []
    context, page = profile(blank)
    def extra_activity(route):
        route.fulfill(status=200, json=model_output(route.request.post_data_json, extra=True))
    context.route('**/api/constraints/parse', extra_activity)
    page.get_by_role('button', name='识别约束', exact=True).click()
    expect(page.locator('.activity-row')).to_have_count(3)
    expect(page.locator('.parse-warning')).to_contain_text('线性代数')
    expect(page.locator('.parse-warning')).to_contain_text('可能是对原文的归纳，请核对')
    expect(page.get_by_label('我已检查并确认当前任务与约束')).not_to_be_checked()
    report['checks'].append('A model-supplied activity absent from the text is clearly flagged for review')
    context.close()

    context, page = profile(template)
    def renamed_activity(route):
        data = model_output(route.request.post_data_json)
        data['problem']['activities'][0]['name'] = '量子物理'
        route.fulfill(status=200, json=data)
    context.route('**/api/constraints/parse', renamed_activity)
    choose(page, '保留现有任务并识别')
    expect(page.locator('.parse-warning')).to_contain_text('量子物理')
    report['checks'].append('An unexpected rename of an existing activity is flagged for review')
    context.close()

    context, page = profile(template)
    page.get_by_label('自然语言需求').fill('安排个人周计划，每天睡8小时，午饭半小时，每周跑步3次。')
    requests = []
    def suggest_then_continue(route):
        payload = route.request.post_data_json
        requests.append(deepcopy(payload))
        if not payload.get('allow_scenario_mismatch'):
            route.fulfill(status=409, json={'detail': {'code': 'scenario_mismatch', 'suggested_scenario': 'life', 'message': '建议切换'}})
        else:
            route.fulfill(status=200, json=model_output(payload))
    context.route('**/api/constraints/parse', suggest_then_continue)
    choose(page, '只使用本次描述')
    hint = page.get_by_role('dialog', name='这段需求更适合个人周计划')
    expect(hint).to_be_visible()
    hint.get_by_role('button', name='仍在当前场景识别').click()
    expect(page.locator('.activity-row')).to_have_count(2)
    assert len(requests) == 2 and all(req['problem']['activities'] == [] for req in requests)
    assert requests[1]['allow_scenario_mismatch'] is True
    report['checks'].append('Explicitly keeping the current scene also keeps the chosen replacement scope')
    context.close()

    context, page = profile(template, {'width': 390, 'height': 844})
    page.get_by_role('button', name='识别约束', exact=True).click()
    dialog = page.get_by_role('dialog', name='如何处理已有任务？')
    expect(dialog.get_by_role('button', name='只使用本次描述')).to_be_visible()
    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    assert dialog.evaluate('(el) => el.scrollWidth <= el.clientWidth')
    if args.screenshot:
        page.screenshot(path=args.screenshot, full_page=True)
    report['checks'].append('Scope choices remain visible without horizontal overflow on mobile')
    context.close()
    api.close()
    browser.close()

assert not report['page_errors'], report['page_errors']
if args.report:
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False), flush=True)
