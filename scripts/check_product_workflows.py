"""Exercise the real website: user workspaces, privacy, backup, review, and re-solving."""
import argparse
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8019')
parser.add_argument('--proxy')
parser.add_argument('--ai', action='store_true')
parser.add_argument('--report')
parser.add_argument('--screenshot')
args = parser.parse_args()
url = args.url.rstrip('/')
report = {'url': url, 'checks': [], 'solves': [], 'page_errors': [], 'console_errors': []}
launch = {'headless': True}
if args.proxy:
    launch['proxy'] = {'server': args.proxy}

with sync_playwright() as p:
    browser = p.chromium.launch(**launch)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
    page.on('console', lambda msg: report['console_errors'].append(msg.text)
            if msg.type == 'error' and 'status of 422' not in msg.text else None)

    def solved(action):
        with page.expect_response(lambda r: r.url.endswith('/api/solve'), timeout=180000) as pending:
            action()
        response = pending.value
        assert response.ok, response.text()
        result = response.json()
        assert result['status'] in ('FEASIBLE', 'OPTIMAL'), result['status']
        assert result['metrics']['hard_violations'] == 0
        expect(page.locator('.busy-status')).to_have_count(0, timeout=15000)
        report['solves'].append({'status': result['status'], 'scheduled': len(result['assignments']),
                                'solve_time': result['metrics']['solve_time'], 'hard_violations': 0})
        return result

    page.goto(url, wait_until='networkidle', timeout=180000)
    expect(page.get_by_role('dialog', name='开始安排你的时间', exact=True)).to_be_visible()
    assert page.evaluate("JSON.parse(localStorage.getItem('optiday.workspace.v1')).workspaces.life.problem.activities.length") == 0
    initial = solved(lambda: page.get_by_role('button', name='体验完整示例', exact=True).click())
    report['checks'].append('a new browser starts blank and loads a full example only after explicit selection')
    assert page.request.get(url + '/api/history').json() == []
    health = page.request.get(url + '/api/health').json()
    assert health['history_scope'] == 'browser'
    report['version'] = health['version']
    report['checks'].append('public server history does not disclose visitor problems or results')

    with page.expect_download() as pending:
        page.get_by_role('button', name='备份工作空间', exact=True).click()
    backup = pending.value
    backup_bytes = Path(backup.path()).read_bytes()
    data = json.loads(backup_bytes)
    assert data['format'] == 'optiday-workspace' and len(data['workspace']['problem']['activities']) == 35
    page.get_by_role('button', name='新建自己的计划', exact=True).click()
    page.get_by_role('dialog').get_by_role('button', name='取消', exact=True).click()
    expect(page.locator('.calendar-event')).to_have_count(28)
    page.get_by_role('button', name='新建自己的计划', exact=True).click()
    page.get_by_role('dialog').get_by_role('button', name='确认新建', exact=True).click()
    expect(page.locator('textarea')).to_have_value('')
    expect(page.locator('.optimize-button')).to_be_disabled()
    assert page.evaluate("JSON.parse(localStorage.getItem('optiday.workspace.v1')).workspaces.life.problem.activities.length") == 0
    page.get_by_role('button', name='撤销修改', exact=True).click()
    expect(page.locator('.calendar-event')).to_have_count(28)
    report['checks'].append('destructive replacement can be cancelled or undone without losing the original plan')

    page.get_by_role('button', name='新建自己的计划', exact=True).click()
    page.get_by_role('dialog').get_by_role('button', name='确认新建', exact=True).click()
    with page.expect_response(lambda r: r.url.endswith('/api/constraints/validate')):
        page.get_by_label('选择计划所在周', exact=True).fill('2026-10-21')
    expect(page.get_by_label('选择计划所在周', exact=True)).to_have_value('2026-10-19')
    page.get_by_role('button', name='添加活动', exact=True).click()
    dialog = page.get_by_role('dialog', name='添加活动', exact=True)
    dialog.get_by_placeholder('例如：社团会议、课程复习').fill('自己的学习任务')
    dialog.get_by_label('时长', exact=True).select_option('2')
    with page.expect_response(lambda r: r.url.endswith('/api/constraints/validate')):
        dialog.get_by_role('button', name='添加并检查约束', exact=True).click()
    page.get_by_label('我已检查并确认当前任务与约束', exact=True).check()
    own = solved(lambda: page.locator('.optimize-button').click())
    assert len(own['assignments']) == 1
    page.get_by_role('button', name='稳健', exact=True).click()
    expect(page.locator('.plan-changes')).to_contain_text('保留 1 · 调整 0 · 新增 0 · 移出 0', timeout=120000)
    expect(page.locator('.busy-status')).to_have_count(0, timeout=120000)
    report['checks'].append('a new personal plan uses the selected Monday and rescheduling reports actual preserved assignments')

    page.get_by_role('button', name='管理资源', exact=True).click()
    dialog = page.get_by_role('dialog', name='管理资源', exact=True)
    expect(dialog.get_by_role('button', name='删除资源', exact=True)).to_be_disabled()
    dialog.get_by_role('button', name='新增资源', exact=True).click()
    dialog.get_by_label('资源名称', exact=True).last.fill('备用个人资源')
    with page.expect_response(lambda r: r.url.endswith('/api/constraints/validate')):
        dialog.get_by_role('button', name='保存资源', exact=True).click()
    expect(page.locator('.review-check input')).not_to_be_checked()
    page.get_by_role('button', name='管理资源', exact=True).click()
    dialog = page.get_by_role('dialog', name='管理资源', exact=True)
    dialog.locator('.resource-manager-item').filter(has_text='备用个人资源').locator('.resource-manager-toggle').click()
    dialog.locator('.resource-manager-item').filter(has_text='备用个人资源').get_by_role('button', name='删除资源', exact=True).click()
    with page.expect_response(lambda r: r.url.endswith('/api/constraints/validate')):
        dialog.get_by_role('button', name='保存资源', exact=True).click()
    report['checks'].append('resource changes are validated, require review, and cannot delete an in-use resource')

    page.get_by_role('button', name='智能排课', exact=True).click()
    page.wait_for_function("JSON.parse(localStorage.getItem('optiday.workspace.v1'))?.workspaces.academic?.problem.activities.length === 0")
    expect(page.locator('textarea')).to_have_value('')
    assert page.evaluate("JSON.parse(localStorage.getItem('optiday.workspace.v1')).workspaces.academic.problem.activities.length") == 0
    page.locator('textarea').fill('原来的排课草稿需要保留')
    page.get_by_role('button', name='个人周计划', exact=True).click()
    academic = page.request.get(url + '/api/templates/academic').json()
    cross = {**data['workspace'], 'problem': academic, 'result': None, 'previous': [],
             'previousProblem': academic, 'input': '备份中的排课输入', 'reviewed': False}
    cross_bytes = json.dumps({'format': 'optiday-workspace', 'version': 1, 'workspace': cross}).encode()
    page.locator('input[aria-label="选择工作空间备份"]').set_input_files(
        {'name': 'cross.json', 'mimeType': 'application/json', 'buffer': cross_bytes})
    page.get_by_role('dialog').get_by_role('button', name='确认恢复', exact=True).click()
    expect(page.locator('textarea')).to_have_value('备份中的排课输入')
    page.get_by_role('button', name='撤销修改', exact=True).click()
    expect(page.locator('textarea')).to_have_value('原来的排课草稿需要保留')
    page.get_by_role('button', name='个人周计划', exact=True).click()
    report['checks'].append('undoing a cross-scenario import restores the overwritten destination workspace')

    # Only this browser contains the named personal task; a second browser profile is independent.
    other = browser.new_context(viewport={'width': 1440, 'height': 1000})
    second = other.new_page()
    second.goto(url, wait_until='networkidle', timeout=180000)
    with second.expect_response(lambda r: r.url.endswith('/api/solve'), timeout=180000):
        second.get_by_role('button', name='体验完整示例', exact=True).click()
    second.get_by_role('button', name='求解历史', exact=True).click()
    expect(second.locator('.history-row')).to_have_count(1)
    expect(second.locator('.history-row')).not_to_contain_text('我的个人周计划')
    page.get_by_role('button', name='求解历史', exact=True).click()
    expect(page.locator('.history-row').filter(has_text='我的个人周计划')).to_have_count(2)
    report['checks'].append('separate browser profiles see only their own locally saved solve history')

    # Cross-device backup import: full data survives, untrusted solved claims do not bypass review.
    second.get_by_role('button', name='调度工作台', exact=True).click()
    second.locator('input[aria-label="选择工作空间备份"]').set_input_files(
        {'name': 'optiday-workspace.json', 'mimeType': 'application/json', 'buffer': backup_bytes})
    second.get_by_role('dialog', name='恢复工作空间备份？', exact=True).get_by_role('button', name='确认恢复', exact=True).click()
    expect(second.locator('.review-check input')).not_to_be_checked()
    expect(second.locator('.optimize-button')).to_be_disabled()
    restored = second.evaluate("JSON.parse(localStorage.getItem('optiday.workspace.v1')).workspaces.life")
    assert len(restored['problem']['activities']) == 35 and restored['result'] is None
    second.reload(wait_until='networkidle')
    expect(second.locator('.review-check input')).not_to_be_checked()
    report['checks'].append('backup restores tasks on another browser and survives reload without accepting imported solver results')
    before = second.evaluate("localStorage.getItem('optiday.workspace.v1')")
    second.locator('input[aria-label="选择工作空间备份"]').set_input_files(
        {'name': 'invalid.json', 'mimeType': 'application/json', 'buffer': b'{invalid'})
    expect(second.locator('.message.error').first).to_contain_text('有效的 JSON')
    assert second.evaluate("localStorage.getItem('optiday.workspace.v1')") == before
    report['checks'].append('invalid backup is rejected without modifying existing browser content')
    other.close()

    blocked = browser.new_context()
    blocked.add_init_script('''const set = Storage.prototype.setItem;
      Storage.prototype.setItem = function(key, value) {
        if (key === 'optiday.history.v1') throw new DOMException('history quota', 'QuotaExceededError');
        return set.call(this, key, value);
      };''')
    warning_page = blocked.new_page()
    warning_page.goto(url, wait_until='networkidle', timeout=180000)
    with warning_page.expect_response(lambda r: r.url.endswith('/api/solve'), timeout=180000):
        warning_page.get_by_role('button', name='体验完整示例', exact=True).click()
    expect(warning_page.locator('.local-save-status')).to_have_text('已保存在此浏览器')
    expect(warning_page.locator('.history-save-warning')).to_contain_text('未能保存求解历史')
    blocked.close()
    report['checks'].append('history-only storage failure stays visible even when workspace autosave succeeds')

    page.locator('.history-row').filter(has_text='我的个人周计划').first.click()
    if args.ai:
        page.locator('textarea').fill('新增一个临时会议，固定在周三19:00开始，持续1小时，占用我的时间。保留已有学习任务。')
        started = time.monotonic()
        with page.expect_response(lambda r: r.url.endswith('/api/constraints/parse'), timeout=180000) as pending:
            page.get_by_role('button', name='识别约束', exact=True).click()
            page.get_by_role('dialog', name='如何处理已有任务？').get_by_role('button', name='保留现有任务并识别').click()
        response = pending.value
        assert response.ok, response.text()
        parsed = response.json()
        assert parsed['provider'] == 'deepseek'
        expect(page.locator('.review-check input')).not_to_be_checked()
        expect(page.locator('.optimize-button')).to_be_disabled()
        page.locator('.review-check input').check()
        result = solved(lambda: page.locator('.optimize-button').click())
        assert len(result['assignments']) >= 2
        report['ai'] = {'provider': parsed['provider'], 'parse_seconds': round(time.monotonic() - started - result['metrics']['solve_time'], 2),
                        'activities': len(parsed['problem']['activities']), 'confirmed_status': result['status']}
        report['checks'].append('official DeepSeek call produces a validated draft, followed by user review and real CP-SAT solving')
    if args.screenshot:
        page.evaluate('window.scrollTo(0, 0)')
        page.screenshot(path=args.screenshot, full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    expect(page.get_by_role('button', name='备份工作空间', exact=True)).to_be_visible()
    report['checks'].append('mobile workspace actions remain visible without page overflow')
    context.close()
    browser.close()
assert not report['page_errors'], report
assert not report['console_errors'], report
if args.report:
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False), flush=True)
