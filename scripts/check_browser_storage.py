"""Real browser persistence checks. Requires Playwright + installed Chromium.

Start the app first, then run:
  python scripts/check_browser_storage.py --url http://127.0.0.1:8017
Use --smoke for deployment verification without repeating all failure cases.
"""
import argparse
import json
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8017')
parser.add_argument('--proxy')
parser.add_argument('--smoke', action='store_true')
parser.add_argument('--report')
parser.add_argument('--screenshot')
args = parser.parse_args()
url = args.url.rstrip('/')
key = 'atlas.workspace.v1'
draft_text = '我的本地草稿：周三19:00有一个会议，文字还没有提交识别。'
task_name = '本地保存测试会议'
expected_version = (Path(__file__).resolve().parent.parent / 'VERSION').read_text(encoding='utf-8').strip()
report = {'url': url, 'version': expected_version, 'checks': [], 'page_errors': [], 'console_errors': []}
launch = {'headless': True, 'viewport': {'width': 1440, 'height': 1000}}
if args.proxy:
    launch['proxy'] = {'server': args.proxy}

def watch(context):
    page = context.new_page()
    requests = []
    page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
    page.on('console', lambda msg: report['console_errors'].append(msg.text) if msg.type == 'error' else None)
    page.on('request', lambda r: requests.append(r.post_data_json) if r.url.endswith('/api/solve') else None)
    return page, requests

def stored(page):
    return page.evaluate('(key) => JSON.parse(localStorage.getItem(key))', key)

def wait_saved(page, expression):
    page.wait_for_function(f'() => {{ try {{ const data = JSON.parse(localStorage.getItem("{key}")); return data && ({expression}); }} catch {{ return false; }} }}')

def fresh(context, expect_saved=True):
    page, requests = watch(context)
    page.goto(url, wait_until='networkidle', timeout=120000)
    expect(page.get_by_role('dialog', name='开始安排你的时间', exact=True)).to_be_visible()
    assert not requests, 'a fresh browser solved a template without user selection'
    assert stored(page)['workspaces']['life']['problem']['activities'] == []
    with page.expect_response(lambda r: r.url.endswith('/api/solve'), timeout=120000) as pending:
        page.get_by_role('button', name='体验完整示例', exact=True).click()
    solved = pending.value.json()
    assert solved['status'] in ['FEASIBLE', 'OPTIMAL'], solved
    assert solved['metrics']['hard_violations'] == 0, solved
    if expect_saved:
        expect(page.locator('.local-save-status')).to_have_text('已保存在此浏览器')
    return page, requests

def reload_saved(page, requests, expected_text, pending=False):
    count = len(requests)
    page.reload(wait_until='networkidle', timeout=120000)
    expect(page.locator('textarea')).to_have_value(expected_text)
    expect(page.locator('.local-save-status')).to_have_text('已保存在此浏览器')
    assert len(requests) == count, 'reloading a saved workspace sent a solve request'
    if pending:
        expect(page.get_by_role('checkbox', name='我已检查并确认当前任务与约束')).not_to_be_checked()
        expect(page.locator('.optimize-button')).to_be_disabled()

with tempfile.TemporaryDirectory(prefix='atlas-browser-storage-') as temp, sync_playwright() as p:
    profile = str(Path(temp) / 'primary')
    context = p.chromium.launch_persistent_context(profile, **launch)
    page, requests = fresh(context)
    assert page.request.get(url + '/api/health').json()['version'] == expected_version
    initial = stored(page)['workspaces']['life']
    assert len(initial['previous']) == 35
    page.locator('textarea').fill(draft_text)
    # Reload immediately after typing; pagehide must also flush the latest text.
    reload_saved(page, requests, draft_text)
    assert stored(page)['workspaces']['life']['result'] == initial['result']
    report['checks'].append('unparsed text and last result survive immediate refresh without solving')
    page.get_by_role('button', name='添加活动', exact=True).click()
    dialog = page.get_by_role('dialog', name='添加活动', exact=True)
    dialog.get_by_label('活动名称', exact=True).fill(task_name)
    dialog.get_by_label('固定开始时间', exact=True).check()
    dialog.get_by_label('开始时间', exact=True).fill('19:00')
    with page.expect_response(lambda r: r.url.endswith('/api/constraints/validate')):
        dialog.get_by_role('button', name='添加并检查约束', exact=True).click()
    expect(dialog).not_to_be_visible()
    page.get_by_role('button', name='稳健', exact=True).click()
    page.locator('.advanced-weights > summary').click()
    slider = page.get_by_role('slider').first
    slider.focus()
    slider.press('End')
    wait_saved(page, 'data.workspaces.life.problem.activities.length === 36 && data.workspaces.life.customWeights?.goal === 120')
    draft = stored(page)['workspaces']['life']
    assert draft['reviewed'] is False and draft['result'] is None
    assert draft['mode'] == 'robust' and len(draft['previous']) == 35
    reload_saved(page, requests, draft_text, pending=True)
    expect(page.get_by_text(task_name, exact=True)).to_be_visible()
    assert stored(page)['workspaces']['life'] == draft
    report['checks'].append('unconfirmed task/constraint draft, custom weights and previous assignments survive refresh')
    if not args.smoke:
        count = len(requests)
        page.get_by_role('button', name='智能排课', exact=True).click()
        wait_saved(page, 'data.workspaces.academic.problem.activities.length === 0')
        assert len(requests) == count, 'an uncached scene solved a template without selection'
        page.locator('textarea').fill('本班课程的本地输入草稿')
        wait_saved(page, 'data.workspaces.academic.input === "本班课程的本地输入草稿"')
        academic = stored(page)['workspaces']['academic']
        count = len(requests)
        page.get_by_role('button', name='个人周计划', exact=True).click()
        expect(page.locator('textarea')).to_have_value(draft_text)
        expect(page.locator('.optimize-button')).to_be_disabled()
        assert len(requests) == count
        assert stored(page)['workspaces']['life'] == draft
        report['checks'].append('scenario switching restores separate workspaces without solving again')
    expect(page.locator('.pending-input')).to_be_visible()
    expect(page.locator('.optimize-button')).to_be_disabled()
    page.get_by_role('button', name='本次仅使用现有任务与约束', exact=True).click()
    page.get_by_role('checkbox', name='我已检查并确认当前任务与约束').check()
    with page.expect_response(lambda r: r.url.endswith('/api/solve'), timeout=120000) as pending:
        page.locator('.optimize-button').click()
    solved = pending.value.json()
    assert requests[-1]['previous'] == draft['previous']
    assert requests[-1]['weights'] == draft['customWeights'] and requests[-1]['mode'] == 'robust'
    assert solved['status'] in ['FEASIBLE', 'OPTIMAL'] and solved['metrics']['hard_violations'] == 0, solved
    aid = next(a['id'] for a in draft['problem']['activities'] if a['name'] == task_name)
    added = next(a for a in solved['assignments'] if a['activity_id'] == aid)
    assert added['start'] == 134 and added['end'] == 136, added
    wait_saved(page, 'data.workspaces.life.result?.assignments.length === 36')
    life_solved = stored(page)['workspaces']['life']
    report['checks'].append('confirmed restored draft solves using saved weights and previous schedule')
    report['solve'] = {'status': solved['status'], 'scheduled': len(solved['assignments']), 'hard_violations': solved['metrics']['hard_violations']}
    if not args.smoke:
        page.get_by_role('button', name='智能排课', exact=True).click()
        expect(page.locator('textarea')).to_have_value(academic['input'])
        wait_saved(page, 'data.active_scenario === "academic"')
    context.close()
    # Close Chromium completely and reopen the actual same on-disk profile.
    context = p.chromium.launch_persistent_context(profile, **launch)
    page, requests = watch(context)
    page.goto(url, wait_until='networkidle', timeout=120000)
    expect(page.locator('.local-save-status')).to_have_text('已保存在此浏览器')
    expect(page.locator('textarea')).to_have_value(draft_text if args.smoke else academic['input'])
    assert not requests, 'reopening Chromium sent a solve request'
    report['checks'].append('closing and reopening browser restores last active scenario from disk')
    if not args.smoke:
        with page.expect_response(lambda r: r.url.endswith('/api/solve'), timeout=120000):
            page.get_by_role('button', name='恢复预置方案', exact=True).click()
            page.get_by_role('dialog').get_by_role('button', name='确认恢复', exact=True).click()
        wait_saved(page, 'data.workspaces.academic.input !== "本班课程的本地输入草稿"')
        assert stored(page)['workspaces']['life'] == life_solved
        report['checks'].append('reset replaces only the current scenario')
        page.get_by_role('button', name='个人周计划', exact=True).click()
        expect(page.locator('textarea')).to_have_value(draft_text)
        # Same browser, different tabs: editing one scenario must not erase
        # another tab's more recent edits to a different scenario.
        second_tab, second_requests = watch(context)
        second_tab.goto(url, wait_until='networkidle', timeout=120000)
        second_tab.get_by_role('button', name='智能排课', exact=True).click()
        second_tab.locator('textarea').fill('另一标签页的课程草稿')
        wait_saved(second_tab, 'data.workspaces.academic.input === "另一标签页的课程草稿"')
        page.locator('textarea').fill('主标签页的个人计划草稿')
        wait_saved(page, 'data.workspaces.life.input === "主标签页的个人计划草稿"')
        assert stored(page)['workspaces']['academic']['input'] == '另一标签页的课程草稿'
        page.get_by_role('button', name='智能排课', exact=True).click()
        expect(page.locator('textarea')).to_have_value('另一标签页的课程草稿')
        page.get_by_role('button', name='个人周计划', exact=True).click()
        page.locator('textarea').fill(draft_text)
        wait_saved(page, 'data.workspaces.life.input === ' + json.dumps(draft_text))
        assert not second_requests
        second_tab.close()
        # Explicitly activate the main workspace after closing the other tab.
        page.get_by_role('button', name='个人周计划', exact=True).click()
        wait_saved(page, 'data.active_scenario === "life"')
        report['checks'].append('multiple tabs preserve each other\'s edits to different scenarios')

        same_tab, same_requests = watch(context)
        same_tab.goto(url, wait_until='networkidle', timeout=120000)
        page.locator('textarea').fill('同一场景主标签页的新需求')
        wait_saved(page, 'data.workspaces.life.input === "同一场景主标签页的新需求"')
        expect(same_tab.locator('.storage-warning')).to_be_visible()
        same_tab.get_by_role('button', name='资源视图', exact=True).click()
        assert stored(same_tab)['workspaces']['life']['input'] == '同一场景主标签页的新需求', 'stale view changes overwrote newer text'
        same_tab.get_by_role('button', name='保留当前编辑', exact=True).click()
        wait_saved(same_tab, 'data.workspaces.life.input === ' + json.dumps(draft_text))
        expect(page.locator('.storage-warning')).to_be_visible()
        page.get_by_role('button', name='打开最新内容', exact=True).click()
        expect(page.locator('textarea')).to_have_value(draft_text)
        expect(page.locator('.storage-warning')).to_have_count(0)
        report['checks'].append('same-scenario stale tabs cannot overwrite newer edits and explicit conflict choices work')

        same_tab.evaluate('''(key) => {
          const data = JSON.parse(localStorage.getItem(key));
          delete data.workspaces.life;
          localStorage.setItem(key, JSON.stringify(data));
        }''', key)
        expect(page.locator('.storage-warning')).to_be_visible()
        expect(page.get_by_role('button', name='打开最新内容', exact=True)).to_be_disabled()
        page.get_by_role('button', name='保留当前编辑', exact=True).click()
        wait_saved(page, 'data.workspaces.life.input === ' + json.dumps(draft_text))
        expect(page.locator('.storage-warning')).to_have_count(0)
        expect(page.locator('.local-save-status')).to_have_text('已保存在此浏览器')
        assert not same_requests
        same_tab.close()
        page.get_by_role('button', name='个人周计划', exact=True).click()
        page.get_by_role('button', name='周日历', exact=True).click()
        report['checks'].append('a workspace deleted in another tab still offers a safe keep-current recovery')

        other = p.chromium.launch_persistent_context(str(Path(temp) / 'other'), **launch)
        other_page, _ = fresh(other)
        assert stored(other_page)['workspaces']['life']['input'] != draft_text
        assert not any(a['name'] == task_name for a in stored(other_page)['workspaces']['life']['problem']['activities'])
        other_page.locator('textarea').fill('另一台电脑自己的草稿')
        reload_saved(page, requests, draft_text)
        other.close()
        report['checks'].append('different browser profiles keep independent content')
        for name, raw in [('invalid-json', '{'), ('invalid-shape', json.dumps({'schema_version': 1, 'active_scenario': 'life', 'workspaces': {'life': {'problem': {'activities': 'invalid'}}}}))]:
            damaged = p.chromium.launch_persistent_context(str(Path(temp) / name), **launch)
            damaged.add_init_script(f'localStorage.setItem({json.dumps(key)}, {json.dumps(raw)})')
            damaged_page, _ = fresh(damaged)
            assert len(stored(damaged_page)['workspaces']['life']['result']['assignments']) == 35
            assert len(stored(damaged_page)['workspaces']['life']['problem']['activities']) == 35
            damaged.close()
        report['checks'].append('malformed stored JSON and invalid workspace shape recover without blank page')
        blocked = p.chromium.launch_persistent_context(str(Path(temp) / 'blocked'), **launch)
        blocked.add_init_script('Storage.prototype.setItem = function() { throw new DOMException("test quota", "QuotaExceededError"); };')
        blocked_page, blocked_requests = watch(blocked)
        blocked_page.goto(url, wait_until='networkidle', timeout=120000)
        with blocked_page.expect_response(lambda r: r.url.endswith('/api/solve'), timeout=120000) as pending:
            blocked_page.get_by_role('button', name='体验完整示例', exact=True).click()
        assert len(pending.value.json()['assignments']) == 35
        expect(blocked_page.locator('.storage-warning')).to_contain_text('浏览器未能保存当前内容')
        expect(blocked_page.locator('.local-save-status')).to_have_text('本地保存不可用')
        blocked.close()
        report['checks'].append('storage quota failure is visible and does not break scheduling')
    expect(page.locator('.calendar-event')).to_have_count(29)
    page.evaluate('window.scrollTo(0, 0)')
    if args.screenshot:
        page.screenshot(path=args.screenshot, full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    expect(page.locator('.local-save-status')).to_have_text('已保存在此浏览器')
    context.close()
assert not report['page_errors'], report
assert not report['console_errors'], report
if args.report:
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False), flush=True)
