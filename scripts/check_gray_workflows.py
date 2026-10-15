"""Gray-test readiness: real imports/validation/CP-SAT, isolated browser storage.

Only network failures, an occupied server, and short test deadlines are simulated.
No model credentials or personal browser data are accessed.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from playwright.sync_api import Error as PlaywrightError, expect, sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:5174')
parser.add_argument('--proxy')
parser.add_argument('--report')
args = parser.parse_args()
url = args.url.rstrip('/')
report = {'url': url, 'checks': [], 'page_errors': [], 'paid_model_calls': 0}
with sync_playwright() as playwright:
    launch = {'headless': True}
    if args.proxy:
        launch['proxy'] = {'server': args.proxy}
    browser = playwright.chromium.launch(**launch)
    api_context = browser.new_context()
    request = api_context.request
    template = request.get(url + '/api/templates/life').json()
    task = deepcopy(next(a for a in template['activities'] if a['category'] == 'study'))
    task.update(id='gray_task', name='Python复习', duration=2, days=[0], window_start=16, window_end=40)
    problem = {**template, 'activities': [task], 'constraints': []}
    solved = request.post(url + '/api/solve', data={'problem': problem, 'reviewed': True}).json()
    assert solved['metrics']['hard_violations'] == 0

    def ws(p=None, text='', result=None):
        return {'problem': deepcopy(p or problem), 'result': deepcopy(result), 'previous': result['assignments'] if result else [],
                'previousProblem': deepcopy(p or problem), 'input': text, 'appliedInput': '', 'mode': 'balanced', 'customWeights': None,
                'reviewed': True, 'summary': [], 'warnings': [], 'inputTab': 'activities', 'view': 'calendar'}

    def profile(workspace=None, others=None, init=None, mobile=False):
        context = browser.new_context(viewport={'width': 390, 'height': 844} if mobile else {'width': 1440, 'height': 1000})
        workspace = workspace or ws()
        s = workspace['problem']['scenario']
        data = {'schema_version': 1, 'active_scenario': s, 'workspaces': {s: workspace, **(others or {})}}
        context.add_init_script('if(!localStorage.getItem("atlas.workspace.v1"))localStorage.setItem("atlas.workspace.v1",' + json.dumps(json.dumps(data, ensure_ascii=False)) + ')')
        if init:
            context.add_init_script(init)
        page = context.new_page()
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.goto(url, wait_until='networkidle', timeout=180000)
        return context, page

    def saved(page, scenario='life'):
        return page.evaluate('(s)=>JSON.parse(localStorage.getItem("atlas.workspace.v1")).workspaces[s]', scenario)

    def submit(page, name):
        dialog = page.get_by_role('dialog')
        with page.expect_response(lambda r: r.url.endswith('/api/constraints/validate')) as pending:
            dialog.get_by_role('button', name=name, exact=True).click()
        assert pending.value.status == 200, pending.value.text()
        expect(dialog).to_have_count(0)

    context, page = profile()
    page.get_by_label('搜索活动或约束').fill('不存在的名称')
    expect(page.locator('.filter-summary')).to_contain_text('原有数据仍保留')
    page.get_by_role('button', name='清除筛选', exact=True).click()
    expect(page.locator('.activity-row')).to_have_count(1)
    page.get_by_label('搜索活动或约束').fill('Python')
    page.get_by_role('button', name='添加活动', exact=True).click()
    page.get_by_label('活动名称', exact=True).fill('新的会议')
    submit(page, '添加并检查约束')
    expect(page.locator('.activity-row').filter(has_text='新的会议')).to_be_visible()
    report['checks'].append('Search has a clear empty state; newly added tasks remain visible')
    context.close()

    categorized = deepcopy(problem)
    categorized['constraints'] = [{'id': 'category_rule', 'label': '学习时间窗', 'type': 'time_window', 'target': 'study',
                                  'level': 'hard', 'day': None, 'start': 16, 'end': 40, 'other': None, 'value': 0, 'source': 'manual'}]
    context, page = profile(ws(categorized))
    page.get_by_role('button', name='编辑活动 Python复习', exact=True).click()
    page.get_by_label('类别', exact=True).select_option('exercise')
    submit(page, '保存修改')
    assert not saved(page)['problem']['constraints']
    expect(page.locator('.toast')).to_contain_text('分类约束已移除')
    page.get_by_role('button', name='撤销修改', exact=True).click()
    assert saved(page)['problem'] == categorized
    report['checks'].append('Changing the last activity category removes orphan category rules visibly and supports Undo')
    context.close()

    context, page = profile(ws(text='已有未提交的原始需求'), mobile=True)
    original = saved(page)
    file = {'name': '需求.txt', 'mimeType': 'text/plain', 'buffer': '周三19:00有一个会议'.encode()}
    field = page.locator('input[type=file][accept=".txt,.pdf"]')
    def extract():
        field.set_input_files(file)
        expect(page.get_by_role('dialog', name='导入文字到输入框')).to_be_visible()
        expect(page.get_by_label('自然语言需求')).to_have_value(original['input'])
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
    extract()
    page.get_by_role('dialog').get_by_role('button', name='取消', exact=True).click()
    assert saved(page) == original
    extract()
    page.get_by_role('button', name='追加到输入', exact=True).click()
    expect(page.get_by_label('自然语言需求')).to_have_value(original['input'] + '\n\n' + file['buffer'].decode())
    page.get_by_role('button', name='撤销修改', exact=True).click()
    assert saved(page) == original
    extract()
    page.get_by_role('button', name='替换输入', exact=True).click()
    expect(page.get_by_label('自然语言需求')).to_have_value(file['buffer'].decode())
    page.get_by_role('button', name='撤销修改', exact=True).click()
    assert saved(page) == original
    report['checks'].append('TXT import previews, cancels, appends or replaces, and Undo restores original input on mobile')
    context.close()

    context, page = profile()
    text = 'a' * 4000 + '\n周三19:00有一个会议。'
    page.get_by_label('自然语言需求').fill(text)
    # Offline parser is not required for the public test: return the current
    # validated model, checking only the client chunk boundary and preservation.
    calls = []
    def parse_stub(route):
        body = route.request.post_data_json
        calls.append(body)
        route.fulfill(status=200, json={'problem': body['problem'], 'summary': [], 'warnings': [], 'provider': 'demo'})
    page.route('**/api/constraints/parse', parse_stub)
    page.locator('.parse-button').click()
    expect(page.locator('.busy-status')).to_have_count(0)
    assert len(calls[0]['text']) == 4000
    expect(page.get_by_label('自然语言需求')).to_have_value(text[4000:])
    report['checks'].append('A newline at the 4000-character boundary cannot create an oversized request or lose the tail')
    context.close()

    priority_problem = deepcopy(problem)
    priority_problem['activities'] = [{**task, 'optional': True, 'priority': 2, 'window_end': 18},
                                      {**task, 'id': 'other', 'name': '另一可选活动', 'optional': True, 'priority': 5, 'window_end': 18}]
    context, page = profile(ws(priority_problem))
    page.get_by_role('button', name='编辑活动 Python复习', exact=True).click()
    page.get_by_label('可选活动优先级').select_option('9')
    page.get_by_role('dialog').get_by_role('button', name='关闭', exact=True).click()
    expect(page.get_by_role('button', name='继续编辑', exact=True)).to_be_visible()
    page.get_by_role('button', name='继续编辑', exact=True).click()
    submit(page, '保存修改')
    result = request.post(url + '/api/solve', data={'problem': saved(page)['problem'], 'reviewed': True}).json()
    assert [a['activity_id'] for a in result['assignments']] == [task['id']]
    assert result['metrics']['hard_violations'] == 0
    report['checks'].append('An optional priority change is protected as a draft and changes the real solver choice')
    context.close()

    context, page = profile(ws(result=solved))
    held = []
    page.route('**/api/solve', lambda route: held.append(route))
    page.locator('.optimize-button').click()
    expect(page.locator('.busy-status')).to_be_visible()
    expect(page.get_by_role('button', name='导出 PDF', exact=True)).to_be_disabled()
    expect(page.get_by_role('button', name='导出 Excel', exact=True)).to_be_disabled()
    expect(page.get_by_role('button', name='下载计划 JSON', exact=True)).to_be_disabled()
    held[0].continue_()
    expect(page.locator('.busy-status')).to_have_count(0, timeout=120000)
    report['checks'].append('Exports cannot interrupt the global busy state during a solve')
    context.close()

    meeting = request.get(url + '/api/templates/meeting').json()
    meeting.update(activities=[], constraints=[])
    context, page = profile(ws(meeting))
    page.get_by_role('button', name='添加活动', exact=True).click()
    assert page.locator('.editor-resource-settings').get_attribute('open') is not None
    page.get_by_label('活动名称', exact=True).fill('会议室讨论')
    submit(page, '添加并检查约束')
    model = saved(page, 'meeting')['problem']
    result = request.post(url + '/api/solve', data={'problem': model, 'reviewed': True}).json()
    assert result['assignments'][0]['room_id'] is not None and result['metrics']['hard_violations'] == 0
    report['checks'].append('A newly created room-booking task really allocates a meeting room')
    context.close()

    context, page = profile(ws(result=solved), init='AbortSignal.timeout = undefined')
    failures = [True]
    def overloaded(route):
        if failures.pop() if failures else False:
            route.fulfill(status=429, json={'detail': '求解服务繁忙，当前内容保留，请稍后重试。'})
        else:
            route.continue_()
    page.route('**/api/solve', overloaded)
    before = saved(page)
    page.locator('.optimize-button').click()
    expect(page.get_by_role('button', name='重试生成', exact=True)).to_be_visible()
    assert saved(page) == before
    page.get_by_role('button', name='重试生成', exact=True).click()
    expect(page.locator('.busy-status')).to_have_count(0, timeout=120000)
    assert saved(page)['result']['metrics']['hard_violations'] == 0
    report['checks'].append('Busy-service errors preserve the last plan and allow a real retry without AbortSignal.timeout support')
    context.close()

    context, page = profile(ws(result=solved))
    original = saved(page)
    page.evaluate('''()=>{const original=window.setTimeout.bind(window);
        window.setTimeout=(handler,delay,...args)=>original(handler,delay===150000?150:delay,...args)}''')
    stalled = []
    page.route('**/api/export/pdf', lambda route: stalled.append(route))
    page.get_by_role('button', name='导出 PDF', exact=True).click()
    expect(page.locator('.message.error').first).to_contain_text('超时')
    expect(page.locator('.busy-status')).to_have_count(0)
    expect(page.get_by_role('button', name='导出 PDF', exact=True)).to_be_enabled()
    assert saved(page) == original
    for route in stalled:
        try:
            route.abort('timedout')
        except PlaywrightError:
            pass  # The browser may already have canceled it through AbortController.
    page.unroute_all(behavior='ignoreErrors')
    report['checks'].append('A stalled binary export times out and restores controls without altering the plan')
    context.close()

    context, page = profile(ws(text='断网时也应保留的输入'))
    page.route('**/api/import/text', lambda route: route.abort('failed'))
    page.locator('input[type=file][accept=".txt,.pdf"]').set_input_files(file)
    expect(page.locator('.message.error').first).to_contain_text('当前内容已保留')
    expect(page.get_by_label('自然语言需求')).to_have_value('断网时也应保留的输入')
    expect(page.locator('.busy-status')).to_have_count(0)
    report['checks'].append('A failed upload restores the controls and preserves input')
    context.close()

    academic = request.get(url + '/api/templates/academic').json()
    academic.update(activities=[], constraints=[])
    context, page = profile(others={'academic': ws(academic)})
    page.evaluate('''()=>{const original=Storage.prototype.setItem;window.restoreStorage=()=>{Storage.prototype.setItem=original};
        Storage.prototype.setItem=function(k,v){if(k==='atlas.workspace.v1')throw new DOMException('full','QuotaExceededError');return original.call(this,k,v)}}''')
    page.get_by_label('自然语言需求').fill('不能丢失的未保存草稿')
    expect(page.locator('.storage-warning').first).to_be_visible()
    page.get_by_role('button', name='智能排课', exact=True).click()
    expect(page.locator('.result-title')).to_contain_text(academic['name'])
    page.locator('.sidebar').get_by_role('button', name='个人周计划', exact=True).click()
    expect(page.get_by_label('自然语言需求')).to_have_value('不能丢失的未保存草稿')
    page.evaluate('window.restoreStorage()')
    page.get_by_label('自然语言需求').fill('不能丢失的未保存草稿，权限已恢复')
    page.reload(wait_until='networkidle')
    expect(page.get_by_label('自然语言需求')).to_have_value('不能丢失的未保存草稿，权限已恢复')
    report['checks'].append('Quota failure keeps drafts across scene switches; restoring storage persists the draft')
    context.close()

    context, page = profile(others={'academic': ws(academic)})
    other = context.new_page()
    other.goto(url, wait_until='networkidle')
    other.evaluate('''()=>{const d=JSON.parse(localStorage.getItem('atlas.workspace.v1'));delete d.workspaces.academic;localStorage.setItem('atlas.workspace.v1',JSON.stringify(d))}''')
    page.get_by_label('自然语言需求').fill('个人新草稿')
    assert not page.evaluate('!!JSON.parse(localStorage.getItem("atlas.workspace.v1")).workspaces.academic')
    report['checks'].append('Saving one scene cannot resurrect a different scene deleted by another tab')
    context.close()

    context, page = profile()
    source = ws(academic)
    backup = json.dumps({'format': 'atlas-workspace', 'version': 1, 'workspace': source}).encode()
    page.locator('input[aria-label="选择工作空间备份"]').set_input_files({'name': 'academic.json', 'mimeType': 'application/json', 'buffer': backup})
    page.get_by_role('dialog').get_by_role('button', name='确认恢复', exact=True).click()
    page.wait_for_function('!!JSON.parse(localStorage.getItem("atlas.workspace.v1")).workspaces.academic')
    other = context.new_page()
    other.goto(url, wait_until='networkidle')
    other.get_by_label('自然语言需求').fill('另一标签页刚刚写入的排课需求')
    expect(page.locator('.storage-warning')).to_be_visible()
    page.get_by_role('button', name='撤销修改', exact=True).click()
    assert saved(page, 'academic')['input'] == '另一标签页刚刚写入的排课需求'
    expect(page.locator('.message.error').first).to_contain_text('没有删除任何内容')
    report['checks'].append('Undoing a cross-scene restore cannot delete a newer edit from another tab')
    context.close()

    long_name = '名' * 100
    long_problem = deepcopy(problem)
    long_problem['activities'][0]['name'] = long_name
    context, page = profile(ws(long_problem))
    page.get_by_role('button', name='重复活动 ' + long_name, exact=True).click()
    page.get_by_role('checkbox', name='周三', exact=True).check()
    page.get_by_role('dialog').get_by_role('button', name='关闭', exact=True).click()
    page.get_by_role('button', name='继续编辑', exact=True).click()
    page.get_by_role('button', name='新增 1 项活动', exact=True).click()
    expect(page.get_by_role('dialog')).to_have_count(0)
    assert len(saved(page)['problem']['activities']) == 2
    assert len(saved(page)['problem']['activities'][1]['name']) <= 100
    report['checks'].append('Repeated tasks protect selected dates and support maximum-length activity names')
    context.close()

    assert not report['page_errors'], report['page_errors']
    browser.close()
report['status'] = 'passed'
if args.report:
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
