"""Exercise branding and recovery of real pre-rename plans, history, and backups."""
import argparse
from copy import deepcopy
import io
import json
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from pypdf import PdfReader

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8028')
parser.add_argument('--report')
parser.add_argument('--screenshot-dir', type=Path)
args = parser.parse_args()
url = args.url.rstrip('/')
report = {'checks': [], 'page_errors': [], 'paid_model_calls': 0}


def text_contrast(first, second):
    def luminance(rgb):
        channels = [int(x) / 255 for x in re.findall(r'\d+', rgb)[:3]]
        linear = [x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4 for x in channels]
        return sum(weight * value for weight, value in zip([.2126, .7152, .0722], linear))
    low, high = sorted([luminance(first), luminance(second)])
    return (high + .05) / (low + .05)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
    page.goto(url, wait_until='networkidle')
    expect(page).to_have_title('OptiDay · 智能调度工作台')
    expect(page.get_by_role('dialog', name='开始安排你的时间')).to_be_visible()
    assert 'ATLAS' not in page.locator('body').inner_text().upper()
    assert 'Σ' not in page.locator('body').inner_text()
    assert page.locator('.brand-mark path').count() == 2
    favicon = page.request.get(url + '/favicon.svg')
    assert favicon.ok and '#365d4c' in favicon.text()
    report['checks'].append('New title, wordmark, clock symbol and favicon share the OptiDay identity')

    with page.expect_response(lambda response: response.url.endswith('/api/solve'), timeout=120000) as pending:
        page.get_by_role('button', name='体验完整示例', exact=True).click()
    solved = pending.value.json()
    assert solved['metrics']['hard_violations'] == 0
    expect(page.locator('.calendar-event').first).to_be_visible()
    colors = page.locator('.calendar-event').evaluate_all('(es)=>es.map(e=>({category:e.className,color:getComputedStyle(e).color,background:getComputedStyle(e).backgroundColor}))')
    ratios = {item['category']: round(text_contrast(item['color'], item['background']), 2) for item in colors}
    assert min(ratios.values()) >= 4.5, ratios
    report['calendar_text_contrast'] = ratios
    report['checks'].append('Sampled calendar category text reaches a 4.5:1 contrast ratio after the palette change')
    if args.screenshot_dir:
        args.screenshot_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(args.screenshot_dir / 'optiday-workspace.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        page.screenshot(path=str(args.screenshot_dir / 'optiday-mobile.png'), full_page=True)
    context.close()

    api = browser.new_context()
    problem = api.request.get(url + '/api/templates/life').json()
    task = deepcopy(problem['activities'][0])
    task.update(id='upgrade_task', name='保留的旧版任务', duration=2, category='study', days=[0],
                window_start=16, window_end=24, resources=['me'], group=None)
    problem.update(name='保留的旧版计划', activities=[task], constraints=[])
    result = api.request.post(url + '/api/solve', data={'problem': problem, 'reviewed': True}).json()
    assert result['metrics']['hard_violations'] == 0
    workspace = {'problem': problem, 'result': result, 'previous': result['assignments'],
                 'previousProblem': problem, 'input': '保留的旧版输入草稿', 'appliedInput': '保留的旧版输入草稿',
                 'mode': 'balanced', 'customWeights': None, 'reviewed': True,
                 'summary': [], 'warnings': [], 'inputTab': 'activities', 'view': 'calendar'}
    store = {'schema_version': 1, 'active_scenario': 'life', 'workspaces': {'life': workspace}}
    history = [{'id': result['run_id'], 'created_at': '2026-10-26T12:00:00Z', 'workspace': workspace}]
    legacy = browser.new_context(viewport={'width': 1440, 'height': 1000})
    legacy.add_init_script('if(!localStorage.getItem("atlas.workspace.v1")) {' +
                          'localStorage.setItem("atlas.workspace.v1",' + json.dumps(json.dumps(store, ensure_ascii=False)) + ');' +
                          'localStorage.setItem("atlas.history.v1",' + json.dumps(json.dumps(history, ensure_ascii=False)) + ');}')
    page = legacy.new_page()
    page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
    page.goto(url, wait_until='networkidle')
    expect(page.get_by_label('自然语言需求')).to_have_value(workspace['input'])
    expect(page.locator('.activity-row').filter(has_text=task['name'])).to_be_visible()
    page.wait_for_function('localStorage.getItem("optiday.workspace.v1") !== null')
    assert page.evaluate('JSON.parse(localStorage.getItem("optiday.workspace.v1")).workspaces.life.problem.name') == problem['name']
    page.reload(wait_until='networkidle')
    expect(page.get_by_label('自然语言需求')).to_have_value(workspace['input'])
    report['checks'].append('Existing browser tasks, draft, result and chosen week survive rename and reload')

    page.get_by_role('button', name='求解历史', exact=True).first.click()
    expect(page.locator('.history-row').filter(has_text=problem['name'])).to_be_visible()
    page.locator('.history-row').filter(has_text=problem['name']).first.click()
    report['checks'].append('History from the previous browser format remains readable and restorable')

    old = {'format': 'atlas-workspace', 'version': 1, 'workspace': workspace}
    page.locator('input[aria-label="选择工作空间备份"]').set_input_files(
        {'name': 'previous-backup.json', 'mimeType': 'application/json', 'buffer': json.dumps(old, ensure_ascii=False).encode()})
    page.get_by_role('dialog', name='恢复工作空间备份？', exact=True).get_by_role('button', name='确认恢复', exact=True).click()
    expect(page.get_by_label('自然语言需求')).to_have_value(workspace['input'])
    with page.expect_download() as download:
        page.get_by_role('button', name='备份工作空间', exact=True).click()
    file = download.value
    backup = json.loads(Path(file.path()).read_text(encoding='utf-8'))
    assert file.suggested_filename.startswith('optiday-workspace-')
    assert backup['format'] == 'optiday-workspace'
    assert backup['workspace']['problem'] == problem
    report['checks'].append('A previous backup restores safely; new backups use OptiDay names and keep the data intact')

    export = api.request.post(url + '/api/export/pdf', data={'problem': problem, 'result': result})
    assert export.ok and 'optiday-' in export.headers['content-disposition']
    metadata = PdfReader(io.BytesIO(export.body())).metadata
    assert metadata.author == 'OptiDay' and metadata.title.startswith('OptiDay')
    report['checks'].append('Export filenames and PDF metadata carry the new product identity')
    assert not report['page_errors'], report
    legacy.close()
    api.close()
    browser.close()

if args.report:
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
