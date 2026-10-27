"""Reproduce the reported wrong-scene workflow; only the explicit model response is stubbed."""
import argparse
from copy import deepcopy
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8029')
parser.add_argument('--report')
parser.add_argument('--screenshot')
args = parser.parse_args()
report = {'checks': [], 'page_errors': [], 'paid_model_calls': 0}
text = (Path(__file__).resolve().parents[1] / 'sample_data/weekly_planning.txt').read_text(encoding='utf-8').strip()


def workspace(problem, raw=''):
    return {'problem': problem, 'result': None, 'previous': [], 'input': raw, 'appliedInput': '',
            'mode': 'balanced', 'customWeights': None, 'reviewed': False, 'summary': [], 'warnings': [],
            'inputTab': 'activities', 'view': 'calendar'}


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    api = browser.new_context()
    production = api.request.get(args.url + '/api/templates/production').json()
    production.update(activities=[], constraints=[])
    life = api.request.get(args.url + '/api/templates/life').json()
    task = deepcopy(next(a for a in life['activities'] if a['category'] == 'study'))
    task.update(id='kept', name='原有个人任务', duration=2, days=[0])
    life.update(activities=[task], constraints=[])

    def profile(with_existing=True):
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        store = {'schema_version': 1, 'active_scenario': 'production',
                 'workspaces': {'production': workspace(production, text)}}
        if with_existing:
            store['workspaces']['life'] = workspace(life, '尚未识别的原有个人草稿')
        context.add_init_script('if(!localStorage.getItem("optiday.workspace.v1"))localStorage.setItem("optiday.workspace.v1",' + json.dumps(json.dumps(store, ensure_ascii=False)) + ')')
        page = context.new_page()
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.goto(args.url, wait_until='networkidle')
        return context, page

    context, page = profile()
    with page.expect_response(lambda r: r.url.endswith('/api/constraints/parse')) as pending:
        page.get_by_role('button', name='识别约束', exact=True).click()
    assert pending.value.status == 409
    modal = page.get_by_role('dialog', name='这段需求更适合个人周计划')
    expect(modal).to_be_visible()
    expect(page.get_by_label('自然语言需求')).to_have_value(text)
    if args.screenshot:
        page.screenshot(path=args.screenshot, full_page=True)
    report['checks'].append('A personal weekly request in the production scene gets a clear suggestion before a model call')
    modal.get_by_role('button', name='关闭', exact=True).click()
    expect(page.get_by_label('自然语言需求')).to_have_value(text)
    report['checks'].append('Cancelling the suggestion preserves the complete input')

    page.get_by_role('button', name='识别约束', exact=True).click()
    page.get_by_role('button', name='切换并带入需求', exact=True).click()
    expect(page.locator('.scenario-nav.selected')).to_have_text('个人周计划')
    expect(page.get_by_label('自然语言需求')).to_have_value(text)
    page.get_by_role('button', name=re.compile(r'^活动')).click()
    expect(page.locator('.activity-row').filter(has_text='原有个人任务')).to_be_visible()
    page.wait_for_function('JSON.parse(localStorage.getItem("optiday.workspace.v1")).active_scenario==="life"')
    assert page.evaluate('JSON.parse(localStorage.getItem("optiday.workspace.v1")).workspaces.production.input') == text
    page.get_by_role('button', name='撤销修改', exact=True).click()
    expect(page.get_by_label('自然语言需求')).to_have_value('尚未识别的原有个人草稿')
    report['checks'].append('Switching carries the text without losing either scene or the destination draft; Undo restores it')
    context.close()

    context, page = profile(with_existing=False)
    page.get_by_role('button', name='识别约束', exact=True).click()
    page.get_by_role('button', name='切换并带入需求', exact=True).click()
    expect(page.get_by_label('自然语言需求')).to_have_value(text)
    requests = []
    def result(route):
        requests.append(route.request.post_data_json)
        route.fulfill(status=200, content_type='application/json', body=json.dumps(
            {'problem': life, 'summary': ['模型结果替身：仅验证审核交互'], 'warnings': [], 'provider': 'deepseek', 'requires_review': True, 'parse_attempts': 2}))
    page.route('**/api/constraints/parse', result)
    page.get_by_role('button', name='识别约束', exact=True).click()
    page.get_by_role('button', name=re.compile(r'^活动')).click()
    expect(page.locator('.activity-row').filter(has_text='原有个人任务')).to_be_visible()
    assert requests[-1]['problem']['scenario'] == 'life'
    assert requests[-1]['text'] == text
    expect(page.get_by_label('我已检查并确认当前任务与约束')).not_to_be_checked()
    expect(page.locator('.optimize-button')).to_be_disabled()
    report['checks'].append('After switching, the complete text goes to the correct scene and a recovered draft still requires review')
    context.close()

    context, page = profile()
    page.get_by_role('button', name='识别约束', exact=True).click()
    with page.expect_request(lambda r: r.url.endswith('/api/constraints/parse')) as pending:
        page.get_by_role('button', name='仍在当前场景识别', exact=True).click()
    assert pending.value.post_data_json['allow_scenario_mismatch'] is True
    expect(page.get_by_role('dialog')).to_have_count(0)
    expect(page.get_by_label('自然语言需求')).to_have_value(text)
    report['checks'].append('An explicit user choice can keep the current scene without a suggestion loop or input loss')
    context.close()
    api.close()
    browser.close()

assert not report['page_errors'], report
if args.report:
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
