"""Real API/browser checks for weights, stable rescheduling and form errors."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8018')
parser.add_argument('--proxy')
parser.add_argument('--smoke', action='store_true')
parser.add_argument('--report')
args = parser.parse_args()
url = args.url.rstrip('/')
report = {'url': url, 'checks': [], 'page_errors': [], 'console_errors': []}
options = {'headless': True}
if args.proxy:
    options['proxy'] = {'server': args.proxy}

with sync_playwright() as p:
    browser = p.chromium.launch(**options)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
    # Validation failures are expected network responses, not runtime failures.
    page.on('console', lambda msg: report['console_errors'].append(msg.text) if msg.type == 'error' and 'status of 422' not in msg.text else None)
    sent = []
    page.on('request', lambda r: sent.append(r.post_data_json) if r.url.endswith('/api/solve') else None)
    with page.expect_response(lambda r: r.url.endswith('/api/solve'), timeout=120000) as pending:
        page.goto(url, wait_until='networkidle', timeout=120000)
    initial = pending.value.json()
    assert initial['status'] in ['FEASIBLE', 'OPTIMAL'], initial
    page.locator('.sleep-toggle').click()
    expect(page.locator('.calendar-subbar > span').filter(has_text='睡眠').locator('.dot')).to_have_class('dot slate')
    expect(page.locator('.calendar-event')).to_have_count(35)
    page.locator('.sleep-toggle').click()
    with page.expect_response(lambda r: r.url.endswith('/api/solve'), timeout=120000) as pending:
        page.get_by_role('button', name='稳健', exact=True).click()
    robust = pending.value.json()
    assert sent[-1]['previous'] == initial['assignments']
    assert robust['objective']['stability_applicable'] and robust['objective']['weights']['stability'] == 1000
    assert robust['metrics']['hard_violations'] == 0
    expect(page.locator('.change-count')).to_have_text(f"原活动调整 {robust['metrics']['changed']} 项")
    page.set_viewport_size({'width': 390, 'height': 844})
    toast = page.locator('.toast')
    expect(toast).to_be_visible()
    # Inspect an actual entry-animation frame rather than only its final state.
    toast.evaluate('(el) => { el.style.animation = "none"; void el.offsetWidth; el.style.animation = ""; for (const a of el.getAnimations()) { a.pause(); a.currentTime = 100; } }')
    box = toast.bounding_box()
    assert box['x'] >= 0 and box['x'] + box['width'] <= 390, box
    toast.get_by_role('button', name='关闭提示').click()
    page.set_viewport_size({'width': 1440, 'height': 1000})
    report['checks'].append('mobile toast stays within viewport during its entry animation')
    report['robust_changed'] = robust['metrics']['changed']
    report['checks'].append('switching to robust mode sends the existing schedule and enables stability')
    stability = page.get_by_role('slider', name='最小扰动', exact=False)
    expect(stability).to_have_attribute('max', '1000')
    expect(stability).to_have_value('1000')
    count = len(sent)
    stability.focus()
    stability.press('ArrowLeft')
    expect(stability).to_have_value('999')
    expect(page.locator('.weight-hint')).to_have_text('自定义权重待应用')
    assert len(sent) == count
    report['checks'].append('stability slider matches the real 1000 preset and editing weights does not claim they are applied')
    if not args.smoke:
        with page.expect_response(lambda r: r.url.endswith('/api/solve'), timeout=120000):
            page.get_by_role('button', name='按自定义重新求解', exact=True).click()
        expect(page.locator('.weight-hint')).to_have_text('当前计划已应用自定义权重')
    page.get_by_role('button', name='添加活动', exact=True).click()
    dialog = page.get_by_role('dialog', name='添加活动', exact=True)
    dialog.get_by_label('活动名称', exact=True).fill('   ')
    dialog.get_by_role('button', name='添加并检查约束', exact=True).click()
    expect(dialog.get_by_role('alert')).to_contain_text('不能只填写空格')
    dialog.get_by_label('活动名称', exact=True).fill('社团临时讨论')
    with page.expect_response(lambda r: r.url.endswith('/api/constraints/validate')):
        dialog.get_by_role('button', name='添加并检查约束', exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(page.get_by_role('button', name='按自定义重新求解', exact=True)).to_be_disabled()
    expect(page.locator('.weight-hint')).to_contain_text('确认任务与约束后')
    report['checks'].append('blank task name error is visible in its dialog and unreviewed drafts cannot apply weights')
    page.locator('.input-tabs button').first.click()
    page.get_by_role('button', name='添加约束', exact=True).click()
    dialog = page.get_by_role('dialog', name='添加约束', exact=True)
    dialog.get_by_label('约束说明', exact=True).fill('周三晚间不可用')
    dialog.get_by_label('开始时间', exact=True).fill('18:00')
    with page.expect_response(lambda r: r.url.endswith('/api/constraints/validate')) as pending:
        dialog.get_by_role('button', name='保存约束', exact=True).click()
    assert pending.value.status == 422
    expect(dialog.get_by_role('alert')).to_contain_text('起点早于终点')
    dialog.get_by_label('结束时间', exact=True).select_option('40')
    with page.expect_response(lambda r: r.url.endswith('/api/constraints/validate')) as pending:
        dialog.get_by_role('button', name='保存约束', exact=True).click()
    assert pending.value.status == 200
    expect(dialog).not_to_be_visible()
    expect(page.locator('.main-content > .message.error')).to_have_count(0)
    report['checks'].append('real server validation error is visible in dialog and can be corrected successfully')
    if not args.smoke:
        problem = json.loads(page.evaluate('localStorage.getItem("atlas.workspace.v1")'))['workspaces']['life']['problem']
        first_id = problem['activities'][0]['id']
        for ctype in ['precedence', 'fixed_time', 'deadline']:
            page.get_by_role('button', name='添加约束', exact=True).click()
            dialog = page.get_by_role('dialog', name='添加约束', exact=True)
            dialog.get_by_label('约束说明', exact=True).fill('切换类型校验 ' + ctype)
            if ctype == 'fixed_time':
                dialog.get_by_label('日期', exact=True).select_option('-1')
            dialog.get_by_label('约束类型', exact=True).select_option(ctype)
            if ctype == 'precedence':
                expect(dialog.get_by_label('作用对象', exact=True)).to_have_value(first_id)
                dialog.get_by_label('后续活动', exact=True).select_option(problem['activities'][1]['id'])
            elif ctype == 'fixed_time':
                expect(dialog.get_by_label('日期', exact=True)).to_have_value('0')
                dialog.get_by_label('开始时间', exact=True).fill('00:00')
            else:
                expect(dialog.get_by_label('截止到', exact=True)).to_have_value('48')
                dialog.get_by_label('作用对象', exact=True).select_option(first_id)
            with page.expect_response(lambda r: r.url.endswith('/api/constraints/validate')) as pending:
                dialog.get_by_role('button', name='保存约束', exact=True).click()
            assert pending.value.status == 200, pending.value.text()
            saved = pending.value.request.post_data_json['constraints'][-1]
            if ctype == 'deadline':
                assert saved['end'] == 48
            else:
                assert saved['target'] == first_id
            if ctype == 'fixed_time':
                assert saved['day'] == 0
            expect(dialog).not_to_be_visible()
        report['checks'].append('constraint type switches send the target, day and deadline displayed in the form')
        for scenario, label, color in [('meeting', '会议室预订', 'pink'), ('production', '生产排程', 'orange')]:
            with page.expect_response(lambda r: r.url.endswith('/api/solve'), timeout=120000) as pending:
                page.get_by_role('button', name=label, exact=True).click()
            result = pending.value.json()
            assert result['status'] in ['FEASIBLE', 'OPTIMAL'] and result['metrics']['hard_violations'] == 0
            category = '会议' if scenario == 'meeting' else '工序'
            expect(page.locator('.calendar-subbar > span').filter(has_text=category).locator('.dot')).to_have_class('dot ' + color)
        report['checks'].append('meeting and production legend colors match actual calendar events')
        template = page.request.get(url + '/api/templates/life').json()
        precise_deadline = next(c for c in template['constraints'] if c['type'] == 'deadline')
        precise_deadline['end'] = 120
        precise_deadline['label'] = '周三 12:00 高数作业截止'
        response = page.request.post(url + '/api/solve', data={'problem': template, 'reviewed': True, 'mode': 'balanced'})
        assert response.ok, response.text()
        precise_result = response.json()
        assert precise_result['status'] in ['FEASIBLE', 'OPTIMAL']
        with page.expect_response(lambda r: r.url.endswith('/api/history')) as pending:
            page.get_by_role('button', name='求解历史', exact=True).click()
        rows = pending.value.json()
        index = next(i for i, row in enumerate(rows) if row['id'] == precise_result['run_id'])
        expect(page.locator('.history-row')).to_have_count(len(rows))
        page.locator('.history-row').nth(index).click()
        card = page.locator('.constraint-card').filter(has_text=precise_deadline['label'])
        card.get_by_role('button', name='编辑 ' + precise_deadline['label'], exact=True).click()
        deadline_dialog = page.get_by_role('dialog', name='编辑约束', exact=True)
        expect(deadline_dialog.get_by_label('截止到', exact=True)).to_have_value('120')
        expect(deadline_dialog.locator('select[aria-label="截止到"] option:checked')).to_have_text('周三 12:00')
        deadline_dialog.get_by_role('button', name='关闭', exact=True).click()
        report['checks'].append('editing an existing midday deadline displays its exact stored time')
        sleep_activities = [a for a in template['activities'] if a['category'] == 'sleep']
        for a in sleep_activities:
            a['duration'] = 15
        for mixed in [False, True]:
            if mixed:
                sleep_activities[0]['duration'] = 14
            response = page.request.post(url + '/api/solve', data={'problem': template, 'reviewed': True, 'mode': 'balanced'})
            assert response.ok, response.text()
            result = response.json()
            assert result['status'] in ['FEASIBLE', 'OPTIMAL'] and result['metrics']['hard_violations'] == 0
            with page.expect_response(lambda r: r.url.endswith('/api/history')) as pending:
                page.get_by_role('button', name='求解历史', exact=True).click()
            rows = pending.value.json()
            index = next(i for i, row in enumerate(rows) if row['id'] == result['run_id'])
            expect(page.locator('.history-row')).to_have_count(len(rows))
            page.locator('.history-row').nth(index).click()
            expect(page.locator('.sleep-banner')).to_contain_text('7–7.5 小时 / 段' if mixed else '每段 7.5 小时')
            if mixed:
                expect(page.locator('.sleep-banner')).to_contain_text('时间见全天日历')
        report['checks'].append('sleep banner preserves half-hour precision and reports varying durations truthfully')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert not page.evaluate('document.documentElement.scrollWidth > window.innerWidth')
    browser.close()
assert not report['page_errors'], report
assert not report['console_errors'], report
if args.report:
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False), flush=True)
